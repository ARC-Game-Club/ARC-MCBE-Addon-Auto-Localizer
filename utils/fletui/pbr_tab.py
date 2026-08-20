# -*- coding: utf-8 -*-
"""灵动视效（PBR）适配页。"""
from __future__ import annotations

import json
from pathlib import Path

import flet as ft

from ..json_io import loads_jsonc
from ..manifest_service import apply_pbr_capability, read_manifest
from .base_tab import BaseTab
from .components import SectionCard, confirm, error_toast


class PbrTab(BaseTab):
    def __init__(self, page: ft.Page, config):
        super().__init__(page, config)
        self.status_text = ft.Text("", font_family="Consolas", size=12, selectable=True)
        self.add_btn = ft.FilledButton(
            "添加灵动视效支持",
            icon=ft.Icons.VISIBILITY,
            visible=False,
            on_click=lambda e: self._apply(),
        )
        self.remove_btn = ft.FilledButton(
            "移除灵动视效支持",
            icon=ft.Icons.VISIBILITY_OFF,
            visible=False,
            style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
            on_click=lambda e: self._remove(),
        )
        self.root.content = self.build()
        self.refresh_status()

    def _rp(self) -> Path | None:
        p = Path(self.config.get("resource_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def build(self) -> ft.Control:
        body = ft.Column(
            controls=[
                ft.Text(
                    "使用首屏选中模组的资源包。若该模组没有资源包，本功能不可用。",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                SectionCard("当前状态", self.status_text),
                ft.Row(
                    controls=[
                        self.add_btn,
                        self.remove_btn,
                        ft.OutlinedButton("刷新", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh_status()),
                    ],
                    spacing=10,
                    wrap=True,
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

    def _pbr_enabled(self, rp: Path | None) -> bool | None:
        """True=已启用，False=未启用，None=无法判断。"""
        if rp is None:
            return None
        data, err = read_manifest(rp)
        if err or not isinstance(data, dict):
            return None
        caps = data.get("capabilities", [])
        return "pbr" in caps if isinstance(caps, list) else False

    def _update_action_buttons(self, enabled: bool | None) -> None:
        self.add_btn.visible = enabled is False
        self.remove_btn.visible = enabled is True
        try:
            self.add_btn.update()
            self.remove_btn.update()
        except Exception:
            pass

    def refresh_status(self) -> None:
        rp = self._rp()
        lines = []
        enabled = self._pbr_enabled(rp)
        if rp is None:
            lines.append("✗ 当前模组没有资源包，无法添加灵动视效")
        else:
            lines.append(f"资源包: {rp}")
            data, err = read_manifest(rp)
            if err:
                lines.append(f"✗ {err}")
            else:
                header = data.get("header", {})
                lines.append(f"  名称: {header.get('name', '?')}  版本: {header.get('version', '?')}")
                caps = data.get("capabilities", [])
                lines.append(f"  capabilities: {caps}")
                lines.append("  PBR 状态: " + ("✓ 已启用" if enabled else "✗ 未启用"))
        self.status_text.value = "\n".join(lines)
        self._update_action_buttons(enabled)
        try:
            self.status_text.update()
        except Exception:
            pass

    def _apply(self) -> None:
        rp = self._rp()
        if rp is None:
            error_toast(self.page, "当前模组没有资源包")
            return
        apply_pbr_capability(rp, self.log)
        self.refresh_status()

    def _remove(self) -> None:
        rp = self._rp()
        if rp is None:
            error_toast(self.page, "当前模组没有资源包")
            return
        mf = rp / "manifest.json"
        if not mf.exists():
            error_toast(self.page, "manifest.json 不存在")
            return
        confirm(
            self.page,
            title="确认",
            message="确定移除 pbr capability 吗？",
            on_yes=self._do_remove,
        )

    def _do_remove(self) -> None:
        rp = self._rp()
        if rp is None:
            return
        mf = rp / "manifest.json"
        try:
            data = loads_jsonc(mf.read_text(encoding="utf-8-sig"))
            caps = data.get("capabilities", [])
            if "pbr" in caps:
                caps.remove("pbr")
                data["capabilities"] = caps
                mf.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
                self.log("已移除 pbr capability")
            else:
                self.log("manifest.json 中没有 pbr 条目")
        except Exception as e:
            self.log(f"移除失败: {e}")
        self.refresh_status()
