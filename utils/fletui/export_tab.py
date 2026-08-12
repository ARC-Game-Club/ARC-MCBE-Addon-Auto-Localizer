# -*- coding: utf-8 -*-
"""导出本地化包页。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import flet as ft

from ..cloud_drives import drivers_from
from ..export_service import (
    base_mod_name,
    build_export_filename,
    export_localized_pack,
    sanitize_export_name,
)
from ..languages import DEFAULT_CODE, credit_suffix
from .base_tab import BaseTab
from .components import SectionCard, error_toast, toast


class ExportTab(BaseTab):
    def __init__(self, page: ft.Page, config, file_picker: ft.FilePicker):
        super().__init__(page, config)
        self.file_picker = file_picker
        default_out = config.get("export_dir") or str(Path.home() / "Downloads")
        self.out_field = ft.TextField(label="导出目录", value=default_out, expand=True)
        self.drives = drivers_from(config._data)
        self.drive_switches = {
            drive.id: ft.Switch(
                label=f"上传到{drive.display_name}" + ("并分享" if drive.supports_share else ""),
                value=drive.is_enabled(),
            )
            for drive in self.drives
        }
        self.preview = ft.Text("", font_family="Consolas", size=12, selectable=True)
        self.root.content = self.build()
        self._refresh_preview()

    def _rp(self) -> Path | None:
        p = Path(self.config.get("resource_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def _bp(self) -> Path | None:
        p = Path(self.config.get("behavior_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def _mod_name(self) -> str:
        name = (self.config.get("current_mod_name") or "").strip()
        if name:
            return name
        bp, rp = self._bp(), self._rp()
        if bp:
            return bp.name
        if rp:
            return rp.name
        return "unnamed_mod"

    def _credit(self) -> str:
        return (self.config.get("translator_credit") or "DEVILENMO").strip() or "DEVILENMO"

    def _target_code(self) -> str:
        code = (self.config.get("target_language") or DEFAULT_CODE).strip()
        return code or DEFAULT_CODE

    def build(self) -> ft.Control:
        body = ft.Column(
            controls=[
                ft.Text(
                    "将当前模组导出为可双击导入的压缩包：\n"
                    "· 同时有资源包与行为包 → .mcaddon\n"
                    "· 仅有一侧 → .mcpack\n"
                    "二者本质都是 ZIP，仅后缀不同。\n"
                    "勾选下方网盘开关可在导出后自动上传 / 分享。",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                SectionCard(
                    "导出预览",
                    self.preview,
                    ft.OutlinedButton("刷新预览", icon=ft.Icons.REFRESH, on_click=lambda e: self._refresh_preview()),
                ),
                ft.Row(
                    controls=[
                        self.out_field,
                        ft.OutlinedButton("浏览...", icon=ft.Icons.FOLDER_OPEN, on_click=self._browse_out),
                    ],
                    spacing=8,
                ),
                ft.Column(controls=list(self.drive_switches.values()), spacing=4, tight=True),
                ft.FilledButton(
                    "导出本地化包",
                    icon=ft.Icons.ARCHIVE,
                    on_click=lambda e: self._export(),
                ),
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

    def _refresh_preview(self) -> None:
        rp, bp = self._rp(), self._bp()
        credit = self._credit()
        code = self._target_code()
        mod = sanitize_export_name(base_mod_name(self._mod_name()))
        both = rp is not None and bp is not None
        filename = build_export_filename(mod, credit, both, code)
        lines = [
            f"模组: {mod}",
            f"署名: {credit_suffix(code, credit)}",
            f"资源包: {rp.name if rp else '（无）'}",
            f"行为包: {bp.name if bp else '（无）'}",
            f"输出文件: {filename}",
        ]
        if both:
            lines.append(f"结构: {filename}")
            lines.append(f"         ├─ {mod}BP/")
            lines.append(f"         └─ {mod}RP/")
        else:
            lines.append("结构: 包内容直接位于压缩包根目录（含 manifest.json）")
        self.preview.value = "\n".join(lines)
        try:
            self.preview.update()
        except Exception:
            pass

    async def _browse_out(self, e) -> None:
        path = await self.file_picker.get_directory_path(
            dialog_title="选择导出目录",
            initial_directory=self.out_field.value or str(Path.home()),
        )
        if path:
            self.out_field.value = path
            self.out_field.update()
            self.config.set(path, "export_dir")
            self.config.save()

    def _export(self) -> None:
        out = Path((self.out_field.value or "").strip())
        if not out.exists():
            try:
                out.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                error_toast(self.page, f"无法创建导出目录: {err}")
                return
        if self._rp() is None and self._bp() is None:
            error_toast(self.page, "当前模组没有可用包")
            return
        self.config.set(str(out), "export_dir")
        for drive in self.drives:
            drive.cfg["enabled"] = bool(self.drive_switches[drive.id].value)
        self.config.save()
        self._refresh_preview()
        self.run_in_thread(self._export_worker, out)

    def _export_worker(self, out: Path) -> None:
        self.log("=" * 50)
        self.log("开始导出本地化包 …")
        try:
            dest = export_localized_pack(
                out_dir=out,
                mod_name=self._mod_name(),
                credit=self._credit(),
                rp=self._rp(),
                bp=self._bp(),
                log=self.log,
                code=self._target_code(),
            )
        except Exception as err:
            self.log(f"导出失败: {err}")
            error_toast(self.page, f"导出失败: {err}")
            return
        self.log(f"完成: {dest}")
        folder = dest.parent
        results = self._publish_export(dest)
        ok = sum(1 for r in results if r.ok)

        def open_folder(_=None):
            self._open_folder(folder)

        extra = f"，已上传 {ok} 个网盘" if results else ""
        toast(
            self.page,
            f"已导出: {dest.name}{extra}",
            action_label="打开文件夹",
            on_action=open_folder,
        )

    def _publish_export(self, dest: Path):
        chosen = [d for d in self.drives if d.is_enabled()]
        if not chosen:
            return []
        results = []
        for drive in chosen:
            if not drive.is_authorized():
                self.log(f"{drive.display_name}未登录，已跳过。请到设置里完成授权 / 填写 Cookie。")
                continue
            self.log(f"开始发布到{drive.display_name} …")
            result = drive.publish(dest, log=self.log)
            self.config.save()
            results.append(result)
            self.log(result.summary())
            if result.share and result.share.url:
                self.log(f"  分享链接: {result.share.url}")
                if result.share.password:
                    self.log(f"  提取码: {result.share.password}")
        failed = [r for r in results if not r.ok]
        if failed:
            error_toast(self.page, "；".join(r.summary() for r in failed))
        return results

    @staticmethod
    def _open_folder(folder: Path) -> None:
        folder = Path(folder)
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError:
            pass
