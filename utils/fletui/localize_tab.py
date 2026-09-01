# -*- coding: utf-8 -*-
"""模组本地化页：格式化 + display_name 标准化 / 语言 / 脚本 / 署名。"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

import flet as ft

from ..credit_service import apply_credit_to_mod, format_credit_suffix
from ..display_name_service import standardize_display_names_for_mod
from ..format_service import (
    collect_format_targets,
    format_js_files_in,
    format_json_files_in,
)
from ..lang_files import (
    copy_lang_to_target,
    ensure_language_in_languages,
    lang_file_needs_translation,
    parse_lang_content,
    read_lang_map,
    rebuild_lang_lines,
    sync_missing_keys_from_en_us,
)
from ..languages import DEFAULT_CODE, label_of
from ..llm_service import translate_lang_batch
from ..manifest_service import normalize_manifest_header_keys
from ..pack_rename_service import sync_mod_pack_folder_names
from ..paths import resolve_pack_dir
from ..script_localize_service import localize_scripts_in
from ..text_utils import needs_translation
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

    def _target_code(self) -> str:
        code = (self.config.get("target_language") or DEFAULT_CODE).strip()
        return code or DEFAULT_CODE

    def _lang_label(self) -> str:
        return label_of(self._target_code())

    def _await_format(self) -> None:
        """本地化步骤须等进页自动规范化结束，避免日志交错、读写打架。"""
        if self._format_ready.is_set():
            return
        self.log("等待 JSON/JS 规范化完成…")
        self._format_ready.wait()

    def _rp(self) -> Path | None:
        return resolve_pack_dir(self.config.get("resource_pack_path"))

    def _bp(self) -> Path | None:
        return resolve_pack_dir(self.config.get("behavior_pack_path"))

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
        code = self._target_code()
        lang = self._lang_label()
        suffix = format_credit_suffix(credit, code)
        self.credit_btn = ft.FilledTonalButton(
            f"④ 本地化者署名（{suffix}）",
            icon=ft.Icons.BADGE,
            on_click=lambda e: self.run_credit(),
        )

        steps = SectionCard(
            f"本地化步骤（→ {lang}）",
            ft.FilledButton(
                "① Display Name 标准化",
                icon=ft.Icons.LABEL,
                on_click=lambda e: self.run_display_name(),
            ),
            ft.FilledButton(
                f"② 语言文件翻译（→ {lang}）",
                icon=ft.Icons.TRANSLATE,
                on_click=lambda e: self.run_lang(),
            ),
            ft.FilledButton(
                "③ 脚本提示本地化",
                icon=ft.Icons.CODE,
                on_click=lambda e: self.run_scripts(),
            ),
            self.credit_btn,
            ft.FilledButton(
                "⚡ 一键本地化（标准化 + 语言 + 脚本 + 署名）",
                icon=ft.Icons.BOLT,
                on_click=lambda e: self.run_all(),
            ),
        )

        body = ft.Column(
            controls=[
                ft.Text(
                    "进入本页后会自动规范化 JSON / JS。下方按步骤执行，或使用一键本地化。"
                    "图片本地化请到侧栏「图片本地化」页。"
                    f"当前目标语言：{lang}（{code}）。",
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
            self._set_format_label("格式化: 扫描文件…")

            # 先扫完再处理，便于全局进度条；扫描卡住时日志里能看到卡在哪一包
            targets: list[tuple[str, Path, list, list]] = []
            for label, root in packs:
                name = root.name or str(root)
                self.log(f"—— {label}: {name} ——")
                self.log(f"  路径: {root}")
                try:
                    jsons, jss = collect_format_targets(root, log=self.log)
                except Exception as e:
                    self.log(f"  扫描异常: {e}\n{traceback.format_exc()}")
                    self._set_format_label(f"格式化扫描失败: {e}", ft.Colors.ERROR)
                    return
                targets.append((label, root, jsons, jss))

            grand_total = sum(len(j) + len(s) for _, _, j, s in targets)
            if grand_total == 0:
                msg = "格式化完成：无可处理的 JSON/JS"
                self.log(msg)
                self._set_format_label(msg, ft.Colors.PRIMARY)
                self.set_progress(0, 0)
                return

            def on_progress(done: int, total: int, rel: str) -> None:
                # 大包文件很多，避免每个文件都刷 UI
                if done not in (0, total) and done % 8 != 0:
                    return
                self.set_progress(done, total)
                short = Path(rel).name
                self._set_format_label(f"格式化中 {done}/{total}: {short}")

            total_ok = total_fail = total_skip = 0
            offset = 0
            for label, root, jsons, jss in targets:
                self.log(f"—— 处理 {label}: JSON {len(jsons)} / JS {len(jss)} ——")
                ok_j, fail_j, skip_j = format_json_files_in(
                    root,
                    indent=4,
                    log=self.log,
                    on_progress=on_progress,
                    files=jsons,
                    progress_offset=offset,
                    progress_total=grand_total,
                )
                offset += len(jsons)
                ok_s, fail_s, skip_s = format_js_files_in(
                    root,
                    log=self.log,
                    on_progress=on_progress,
                    files=jss,
                    progress_offset=offset,
                    progress_total=grand_total,
                )
                offset += len(jss)
                total_ok += ok_j + ok_s
                total_fail += fail_j + fail_s
                total_skip += skip_j + skip_s
                self.log(
                    f"  JSON {ok_j} 成功 / {fail_j} 失败 / {skip_j} 跳过；"
                    f"JS {ok_s} 成功 / {fail_s} 失败 / {skip_s} 跳过"
                )

            self.set_progress(grand_total, grand_total)
            msg = f"格式化完成：成功 {total_ok}，失败 {total_fail}，跳过 {total_skip}"
            self.log(msg)
            color = ft.Colors.ERROR if total_fail else ft.Colors.PRIMARY
            self._set_format_label(msg, color)
        except Exception as e:
            self.log(f"规范化异常: {e}\n{traceback.format_exc()}")
            self._set_format_label(f"格式化失败: {e}", ft.Colors.ERROR)
        finally:
            self._format_ready.set()

    def run_display_name(self) -> None:
        if not self._packs():
            error_toast(self.page, "当前模组没有可用包")
            return
        self.run_in_thread(self._display_name_worker)

    def _display_name_worker(self) -> None:
        self._await_format()
        code = self._target_code()
        self.log("=" * 50)
        self.log(f"Display Name 标准化（→ {self._lang_label()} / {code}）…")
        llm_cfg = self.config.get("text_llm")
        found, std, fb = standardize_display_names_for_mod(
            self._packs(), code, self.log, llm_cfg=llm_cfg
        )
        self.log(
            f"Display Name 结束：找到 {found}，标准化 {std}，回退直译 {fb}"
        )

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
        code = self._target_code()
        lang = self._lang_label()
        self.log("=" * 50)
        self.log(f"开始语言文件翻译（→ {lang}）…")
        for label, pack in self._packs():
            self.log(f"—— {label}: {pack.name} ——")
            normalize_manifest_header_keys(pack, self.log, code=code)
            texts = pack / "texts"
            if not texts.is_dir():
                self.log("  无 texts/，跳过语言文件")
                continue
            ensure_language_in_languages(texts, code, self.log)
            target = copy_lang_to_target(texts, code, self.log)
            if target is not None:
                sync_missing_keys_from_en_us(texts, code, self.log)
                self._translate_target_lang(target, texts, code, lang)
        self.log("语言文件翻译结束")
        self._sync_folder_names()

    def _sync_folder_names(self) -> None:
        self.log("按本地化包名同步文件夹 …")
        n = sync_mod_pack_folder_names(self._rp(), self._bp(), self.config, self.log)
        if n and self._on_pack_paths_changed is not None:
            try:
                self._on_pack_paths_changed()
            except Exception as e:
                self.log(f"刷新界面路径失败: {e}")

    def _translate_target_lang(
        self, target: Path, texts: Path, code: str, lang: str
    ) -> None:
        orig_text = target.read_text(encoding="utf-8")
        parsed = parse_lang_content(orig_text)
        en_map = read_lang_map(texts / "en_US.lang")

        from ..languages import get as get_lang

        script = get_lang(code).script
        entries = []
        for kind, key, value in parsed:
            if kind != "entry" or key is None:
                continue
            en_val = en_map.get(key)
            if en_val is not None and value == en_val:
                # 与英文源相同：目标若是英语则跳过，否则待译
                if not code.startswith("en"):
                    entries.append((key, value))
            elif needs_translation(value, code):
                # 无 en_US 对照，或已与英文不同但仍像源语言（CJK 等）
                if en_val is None or script != "latin":
                    entries.append((key, value))

        total = len(entries)
        self.log(f"翻译 {target.name}，待译 {total} 条")
        if total == 0:
            if lang_file_needs_translation(target, code):
                self.log("  （检测仍可能有待译内容，但过滤器未命中条目）")
            else:
                self.log(f"  无需翻译（可能已是{lang}）")
            return
        all_translated = {}
        batch_total = (total + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        for i in range(0, total, self.BATCH_SIZE):
            if self._stop_flag.is_set():
                self.log("翻译已停止")
                break
            batch = entries[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            batch_label = f"语言翻译批次 {batch_num}/{batch_total}（{len(batch)} 条）"
            self.set_working(f"翻译批次 {batch_num}/{batch_total}，等待 LLM…")
            self.log(
                f"  批次 {batch_num}/{batch_total}: "
                f"{i + 1}-{min(i + self.BATCH_SIZE, total)}"
            )
            result = translate_lang_batch(
                batch,
                self.config.get("text_llm"),
                self.log,
                lang_label=lang,
                batch_label=batch_label,
            )
            all_translated.update(result)
            self.set_progress(min(i + self.BATCH_SIZE, total), total)
        new_content = rebuild_lang_lines(orig_text, parsed, all_translated)
        target.write_text(new_content, encoding="utf-8")
        self.log(f"已写入 {target.name}")

    def run_scripts(self) -> None:
        bp = self._bp()
        if bp is None:
            error_toast(self.page, "当前模组没有行为包，无法本地化脚本")
            return
        if not self.config.get("text_llm", "api_key"):
            error_toast(self.page, "请先在设置中填写文本翻译 API Key")
            return
        self.run_in_thread(self._scripts_worker, bp)

    def _scripts_worker(self, root: Path) -> None:
        self._await_format()
        code = self._target_code()
        lang = self._lang_label()
        self.log("=" * 50)
        self.log(f"脚本提示本地化（→ {lang}）：{root}")
        files, hits, written, failed = localize_scripts_in(
            root,
            self.config.get("text_llm"),
            self.log,
            lang_label=lang,
            target_code=code,
        )
        self.log(
            f"脚本本地化结束：文件 {files}，命中 {hits}，写入 {written}，失败回退 {failed}"
        )
        if failed:
            error_toast(
                self.page,
                f"有 {failed} 个脚本本地化后格式异常，已自动回退，详见日志",
            )

    def _credit_name(self) -> str:
        return (self.config.get("translator_credit") or "DEVILENMO").strip() or "DEVILENMO"

    def run_credit(self) -> None:
        if not self._packs():
            error_toast(self.page, "当前模组没有可用包")
            return
        credit = self._credit_name()
        code = self._target_code()
        if self.credit_btn is not None:
            self.credit_btn.text = f"④ 本地化者署名（{format_credit_suffix(credit, code)}）"
            self.credit_btn.update()
        self.run_in_thread(self._credit_worker, credit)

    def _credit_worker(self, credit: str) -> None:
        self._await_format()
        code = self._target_code()
        self.log("=" * 50)
        self.log(f"应用署名: {format_credit_suffix(credit, code)}")
        n = apply_credit_to_mod(self._rp(), self._bp(), credit, self.log, code=code)
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
        self.log("一键本地化开始")
        self._display_name_worker()
        self._lang_worker()
        bp = self._bp()
        if bp is not None:
            self._scripts_worker(bp)
        self._credit_worker(self._credit_name())
        self.log("一键本地化结束")
