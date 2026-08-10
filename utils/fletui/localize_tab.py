# -*- coding: utf-8 -*-
"""模组汉化页：格式化 + 语言 / display_name / 脚本 / 署名。"""
from __future__ import annotations

import threading
from pathlib import Path

import flet as ft

from .. import PROJECT_ROOT
from ..credit_service import apply_credit_to_mod
from ..display_name_service import (
    apply_display_name_map,
    extract_display_names,
    translate_display_name_map,
)
from ..format_service import format_js_files_in, format_json_files_in
from ..lang_files import (
    copy_lang_to_zh_cn,
    ensure_zh_cn_in_languages,
    lang_file_needs_translation,
    parse_lang_content,
    rebuild_lang_lines,
)
from ..llm_service import translate_lang_batch
from ..pack_rename_service import sync_mod_pack_folder_names
from ..script_localize_service import localize_scripts_in
from ..text_utils import is_english_text
from .base_tab import BaseTab
from .components import SectionCard, error_toast


class LocalizeTab(BaseTab):
    BATCH_SIZE = 50

    def __init__(self, page: ft.Page, config, on_pack_paths_changed=None):
        super().__init__(page, config)
        self._on_pack_paths_changed = on_pack_paths_changed
        self._format_ready = threading.Event()
        self.format_label = ft.Text("格式化: 进行中…", size=13)
        self.credit_btn: ft.FilledButton | None = None
        self.root.content = self.build()
        self.page.run_thread(self._auto_format_worker)

    def _await_format(self) -> None:
        """汉化步骤须等进页自动规范化结束，避免日志交错、读写打架。"""
        if self._format_ready.is_set():
            return
        self.log("等待 JSON/JS 规范化完成…")
        self._format_ready.wait()

    def _rp(self) -> Path | None:
        p = Path(self.config.get("resource_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def _bp(self) -> Path | None:
        p = Path(self.config.get("behavior_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def _packs(self) -> list[tuple[str, Path]]:
        out = []
        rp, bp = self._rp(), self._bp()
        if rp:
            out.append(("资源包", rp))
        if bp:
            out.append(("行为包", bp))
        return out

    def build(self) -> ft.Control:
        credit = (self.config.get("translator_credit") or "DEVILENMO").strip()
        self.credit_btn = ft.FilledTonalButton(
            f"④ 汉化者署名（{credit}汉化）",
            icon=ft.Icons.BADGE,
            on_click=lambda e: self.run_credit(),
        )

        steps = SectionCard(
            "汉化步骤",
            ft.FilledButton(
                "① 语言文件汉化",
                icon=ft.Icons.TRANSLATE,
                on_click=lambda e: self.run_lang(),
            ),
            ft.FilledButton(
                "② Display Name 汉化",
                icon=ft.Icons.LABEL,
                on_click=lambda e: self.run_display_name(),
            ),
            ft.FilledButton(
                "③ 脚本提示汉化",
                icon=ft.Icons.CODE,
                on_click=lambda e: self.run_scripts(),
            ),
            self.credit_btn,
            ft.FilledButton(
                "⚡ 一键汉化（语言 + Display Name + 脚本 + 署名）",
                icon=ft.Icons.BOLT,
                on_click=lambda e: self.run_all(),
            ),
        )

        body = ft.Column(
            controls=[
                ft.Text(
                    "进入本页后会自动规范化 JSON / JS。下方按步骤执行，或使用一键汉化。"
                    "图片汉化请到侧栏「图片汉化」页。",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                self.format_label,
                steps,
                self.make_progress_row(),
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        return ft.Column(
            controls=[body, self.make_log_panel()],
            spacing=12,
            expand=True,
        )

    def _set_format_label(self, text: str, color=None) -> None:
        self.format_label.value = text
        self.format_label.color = color
        try:
            self.format_label.update()
        except Exception:
            pass

    def _auto_format_worker(self) -> None:
        self._format_ready.clear()
        try:
            packs = self._packs()
            if not packs:
                self._set_format_label("格式化: 无可用包", ft.Colors.ERROR)
                return
            self.log("=" * 50)
            self.log("自动规范化 JSON / JS …")
            total_ok = total_fail = 0
            for label, root in packs:
                self.log(f"—— {label}: {root.name} ——")
                ok_j, fail_j = format_json_files_in(root, indent=4, log=self.log)
                ok_s, fail_s = format_js_files_in(root, log=self.log)
                total_ok += ok_j + ok_s
                total_fail += fail_j + fail_s
                self.log(f"  JSON {ok_j} 成功 / {fail_j} 失败；JS {ok_s} 成功 / {fail_s} 失败")
            msg = f"格式化完成：成功 {total_ok}，失败 {total_fail}"
            self.log(msg)
            self._set_format_label(msg, ft.Colors.PRIMARY)
        finally:
            self._format_ready.set()

    def run_lang(self) -> None:
        if not self._packs():
            error_toast(self.page, "当前模组没有可用的资源包或行为包")
            return
        if not self.config.get("text_llm", "api_key"):
            error_toast(self.page, "请先在设置中填写文本翻译 API Key")
            return
        self.run_in_thread(self._lang_worker)

    def _lang_worker(self) -> None:
        self._await_format()
        self.log("=" * 50)
        self.log("开始语言文件汉化 …")
        for label, pack in self._packs():
            texts = pack / "texts"
            self.log(f"—— {label}: {pack.name} ——")
            if not texts.is_dir():
                self.log("  无 texts/，跳过")
                continue
            ensure_zh_cn_in_languages(texts, self.log)
            zh = copy_lang_to_zh_cn(texts, self.log)
            if zh is None:
                continue
            self._translate_zh_lang(zh)
        self.log("语言文件汉化结束")
        self._sync_folder_names()

    def _sync_folder_names(self) -> None:
        self.log("按中文包名同步文件夹 …")
        n = sync_mod_pack_folder_names(self._rp(), self._bp(), self.config, self.log)
        if n and self._on_pack_paths_changed is not None:
            try:
                self._on_pack_paths_changed()
            except Exception as e:
                self.log(f"刷新界面路径失败: {e}")

    def _translate_zh_lang(self, zh: Path) -> None:
        orig_text = zh.read_text(encoding="utf-8")
        parsed = parse_lang_content(orig_text)
        entries = [
            (key, value)
            for kind, key, value in parsed
            if kind == "entry" and is_english_text(value)
        ]
        total = len(entries)
        self.log(f"翻译 {zh}，待译 {total} 条")
        if total == 0:
            if lang_file_needs_translation(zh):
                self.log("  （检测仍有英文，但过滤器未命中条目）")
            else:
                self.log("  无需翻译（可能已是中文）")
            return
        all_translated = {}
        for i in range(0, total, self.BATCH_SIZE):
            if self._stop_flag.is_set():
                self.log("翻译已停止")
                break
            batch = entries[i:i + self.BATCH_SIZE]
            self.log(
                f"  批次 {i // self.BATCH_SIZE + 1}: "
                f"{i + 1}-{min(i + self.BATCH_SIZE, total)}"
            )
            result = translate_lang_batch(batch, self.config.get("text_llm"), self.log)
            all_translated.update(result)
            self.set_progress(min(i + self.BATCH_SIZE, total), total)
        new_content = rebuild_lang_lines(orig_text, parsed, all_translated)
        zh.write_text(new_content, encoding="utf-8")
        self.log(f"已写入 {zh.name}")

    def run_display_name(self) -> None:
        root = self._bp() or self._rp()
        if root is None:
            error_toast(self.page, "当前模组没有可用包")
            return
        if not self.config.get("text_llm", "api_key"):
            error_toast(self.page, "请先在设置中填写文本翻译 API Key")
            return
        self.run_in_thread(self._display_name_worker, root)

    def _display_name_worker(self, root: Path) -> None:
        self._await_format()
        self.log("=" * 50)
        self.log(f"Display Name 汉化：{root}")
        out_p = PROJECT_ROOT / "display_names_translation.txt"
        processed, found = extract_display_names(root, out_p)
        self.log(f"扫描 {processed} 个 JSON，找到 {found} 条")
        if found == 0:
            self.log("无 display_name，跳过")
            return
        count = translate_display_name_map(out_p, self.config.get("text_llm"), self.log)
        self.log(f"LLM 翻译 {count} 条")
        updated, skipped, not_found = apply_display_name_map(root, out_p, self.log)
        self.log(f"应用完成：更新 {updated}，跳过 {skipped}，未找到 {not_found}")

    def _credit_name(self) -> str:
        return (self.config.get("translator_credit") or "DEVILENMO").strip() or "DEVILENMO"

    def run_scripts(self) -> None:
        bp = self._bp()
        if bp is None:
            error_toast(self.page, "当前模组没有行为包，无法汉化脚本")
            return
        if not self.config.get("text_llm", "api_key"):
            error_toast(self.page, "请先在设置中填写文本翻译 API Key")
            return
        self.run_in_thread(self._scripts_worker, bp)

    def _scripts_worker(self, root: Path) -> None:
        self._await_format()
        self.log("=" * 50)
        self.log(f"脚本提示汉化：{root}")
        files, hits, written, failed = localize_scripts_in(
            root, self.config.get("text_llm"), self.log
        )
        self.log(
            f"脚本汉化结束：文件 {files}，命中 {hits}，写入 {written}，失败回退 {failed}"
        )
        if failed:
            error_toast(self.page, f"有 {failed} 个脚本汉化后格式异常，已自动回退，详见日志")

    def run_credit(self) -> None:
        if not self._packs():
            error_toast(self.page, "当前模组没有可用包")
            return
        credit = self._credit_name()
        if self.credit_btn is not None:
            self.credit_btn.text = f"④ 汉化者署名（{credit}汉化）"
            self.credit_btn.update()
        self.run_in_thread(self._credit_worker, credit)

    def _credit_worker(self, credit: str) -> None:
        self._await_format()
        self.log("=" * 50)
        self.log(f"应用署名: （{credit}汉化）")
        n = apply_credit_to_mod(self._rp(), self._bp(), credit, self.log)
        self.log(f"署名完成：成功 {n} 个包")
        self._sync_folder_names()

    def run_all(self) -> None:
        if not self._packs():
            error_toast(self.page, "当前模组没有可用包")
            return
        if not self.config.get("text_llm", "api_key"):
            error_toast(self.page, "请先在设置中填写文本翻译 API Key")
            return
        self.run_in_thread(self._all_worker)

    def _all_worker(self) -> None:
        self._await_format()
        self.log("=" * 50)
        self.log("一键汉化开始")
        self._lang_worker()
        root = self._bp() or self._rp()
        if root is not None:
            self._display_name_worker(root)
        bp = self._bp()
        if bp is not None:
            self._scripts_worker(bp)
        self._credit_worker(self._credit_name())
        self.log("一键汉化结束")
