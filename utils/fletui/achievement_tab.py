# -*- coding: utf-8 -*-
"""成就兼容：为模组 manifest 写入 metadata.product_type = addon。"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from ..manifest_service import (
    apply_addon_product_type,
    has_addon_product_type,
    read_manifest,
    remove_addon_product_type,
)
from .base_tab import BaseTab
from .components import SectionCard, confirm, error_toast


class AchievementTab(BaseTab):
    def __init__(self, page: ft.Page, config):
        super().__init__(page, config)
        self.status_text = ft.Text("", font_family="Consolas", size=12, selectable=True)
        self.add_btn = ft.FilledButton(
            "添加成就兼容",
            icon=ft.Icons.EMOJI_EVENTS,
            visible=False,
            on_click=lambda e: self._apply(),
        )
        self.remove_btn = ft.FilledButton(
            "移除成就兼容",
            icon=ft.Icons.EVENT_BUSY,
            visible=False,
            style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
            on_click=lambda e: self._remove(),
        )
        self.root.content = self.build()
        self.refresh_status()

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
        body = ft.Column(
            controls=[
                ft.Text(
                    "使用首屏选中模组的资源包 / 行为包。在 manifest.json 写入 "
                    'metadata.product_type = "addon"，使模组以附加包方式加载并保持成就可用。',
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                SectionCard("当前状态", self.status_text),
                ft.Row(
                    controls=[
                        self.add_btn,
                        self.remove_btn,
                        ft.OutlinedButton(
                            "刷新", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh_status()
                        ),
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

    def _pack_states(self) -> list[tuple[str, Path, bool | None]]:
        """每包：(标签, 路径, True已兼容 / False未兼容 / None无法判断)。"""
        states = []
        for label, root in self._packs():
            data, err = read_manifest(root)
            if err or not isinstance(data, dict):
                states.append((label, root, None))
            else:
                states.append((label, root, has_addon_product_type(data)))
        return states

    def _update_action_buttons(self, states: list[tuple[str, Path, bool | None]]) -> None:
        known = [s for _, _, s in states if s is not None]
        if not known:
            self.add_btn.visible = False
            self.remove_btn.visible = False
        else:
            self.add_btn.visible = any(s is False for s in known)
            self.remove_btn.visible = any(s is True for s in known)
        try:
            self.add_btn.update()
            self.remove_btn.update()
        except Exception:
            pass

    def refresh_status(self) -> None:
        lines = []
        states = self._pack_states()
        if not states:
            lines.append("✗ 当前模组没有资源包或行为包，无法设置成就兼容")
        else:
            for label, root, enabled in states:
                lines.append(f"—— {label}: {root.name} ——")
                lines.append(f"  路径: {root}")
                data, err = read_manifest(root)
                if err:
                    lines.append(f"  ✗ {err}")
                    continue
                header = data.get("header", {}) if isinstance(data, dict) else {}
                lines.append(
                    f"  名称: {header.get('name', '?')}  版本: {header.get('version', '?')}"
                )
                md = data.get("metadata") if isinstance(data, dict) else None
                lines.append(f"  metadata: {md}")
                if enabled is True:
                    lines.append('  成就兼容: ✓ 已启用（product_type = "addon"）')
                elif enabled is False:
                    lines.append("  成就兼容: ✗ 未启用")
                else:
                    lines.append("  成就兼容: ? 无法判断")
        self.status_text.value = "\n".join(lines)
        self._update_action_buttons(states)
        try:
            self.status_text.update()
        except Exception:
            pass

    def _apply(self) -> None:
        packs = self._packs()
        if not packs:
            error_toast(self.page, "当前模组没有可用包")
            return
        self.log("=" * 50)
        self.log("添加成就兼容（metadata.product_type = addon）…")
        ok = 0
        for label, root in packs:
            self.log(f"—— {label} ——")
            if apply_addon_product_type(root, self.log):
                ok += 1
        self.log(f"完成：{ok}/{len(packs)} 个包已就绪")
        self.refresh_status()

    def _remove(self) -> None:
        if not self._packs():
            error_toast(self.page, "当前模组没有可用包")
            return
        confirm(
            self.page,
            title="确认",
            message='确定从当前模组各包的 manifest 中移除 product_type = "addon" 吗？',
            on_yes=self._do_remove,
        )

    def _do_remove(self) -> None:
        packs = self._packs()
        if not packs:
            return
        self.log("=" * 50)
        self.log("移除成就兼容…")
        for label, root in packs:
            self.log(f"—— {label} ——")
            remove_addon_product_type(root, self.log)
        self.refresh_status()
