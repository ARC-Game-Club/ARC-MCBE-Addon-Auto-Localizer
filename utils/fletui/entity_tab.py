# -*- coding: utf-8 -*-
"""实体工具页。"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from ..entity_service import add_monster_tags, list_pack_dirs, scan_monster_health
from .base_tab import BaseTab
from .components import SectionCard, error_toast


class EntityTab(BaseTab):
    def __init__(self, page: ft.Page, config):
        super().__init__(page, config)
        bp = self._bp()
        self.path_label = ft.Text(
            f"行为包: {bp}" if bp else "✗ 当前模组没有行为包",
            size=13,
            color=ft.Colors.ERROR if bp is None else None,
        )
        self.result_box = ft.TextField(
            label="扫描结果（可全选复制）",
            multiline=True,
            min_lines=8,
            max_lines=16,
            read_only=True,
            text_size=12,
            value="",
            expand=True,
        )
        self.root.content = self.build()

    def _bp(self) -> Path | None:
        p = Path(self.config.get("behavior_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def build(self) -> ft.Control:
        body = ft.Column(
            controls=[
                ft.Text(
                    "使用首屏选中模组的行为包。若该模组没有行为包，本功能不可用。",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                self.path_label,
                SectionCard(
                    "功能",
                    ft.Row(
                        controls=[
                            ft.FilledButton(
                                "扫描怪物名称 & 血量",
                                icon=ft.Icons.MONITOR_HEART,
                                on_click=lambda e: self._scan_health(),
                            ),
                            ft.FilledTonalButton(
                                "为攻击玩家的实体添加 monster 标签",
                                icon=ft.Icons.PETS,
                                on_click=lambda e: self._add_monster(),
                            ),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                ),
                self.result_box,
            ],
            spacing=12,
            expand=True,
        )
        return ft.Column(
            controls=[body, self.make_log_panel()],
            spacing=12,
            expand=True,
        )

    def _set_result(self, text: str) -> None:
        self.result_box.value = text
        try:
            self.result_box.update()
        except Exception:
            pass

    def _scan_health(self) -> None:
        if self._bp() is None:
            error_toast(self.page, "当前模组没有行为包")
            return
        self.run_in_thread(self._scan_health_worker)

    def _scan_health_worker(self) -> None:
        self.log("=" * 50)
        self.log("扫描怪物名称 & 血量 ...")
        packs = list_pack_dirs(self._bp())
        entries = scan_monster_health(packs, self.log)
        out_lines = []
        for identifier, hp_str, name in entries:
            out_lines.append(f"{identifier}={hp_str}")
            name_part = f"[{name}] " if name else ""
            self.log(f"  {identifier}  →  {name_part}血量 {hp_str}")
        text = "\n".join(out_lines)
        self._set_result(text)
        self.log(f"完成：{len(entries)} 个怪物（结果已填入上方文本框，可直接复制）")

    def _add_monster(self) -> None:
        if self._bp() is None:
            error_toast(self.page, "当前模组没有行为包")
            return
        self.run_in_thread(self._add_monster_worker)

    def _add_monster_worker(self) -> None:
        self.log("=" * 50)
        self.log("扫描需要添加 monster 标签的实体 ...")
        packs = list_pack_dirs(self._bp())
        total = add_monster_tags(packs, self.log)
        self.log(f"完成：共为 {total} 个实体添加 monster 标签")
