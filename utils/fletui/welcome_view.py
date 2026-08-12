# -*- coding: utf-8 -*-
"""启动首屏：模组卡片列表。"""
from __future__ import annotations

import flet as ft

from ..mod_catalog import ModEntry, list_mods
from ..pack_rename_service import apply_pack_renames, plan_pack_renames
from ..paths import get_minecraft_base_dir
from .components import confirm, error_toast, toast
from .theme import brand_gradient


class WelcomeView:
    """首屏：扫描并选择模组。"""

    def __init__(self, page: ft.Page, config, on_enter):
        self.page = page
        self.config = config
        self.on_enter = on_enter
        self._mods: list[ModEntry] = []
        self.count_label = ft.Text("", size=13)
        self.list_view = ft.ListView(expand=True, spacing=8, padding=4)
        self.root = self._build()

    def _build(self) -> ft.Control:
        hero = ft.Container(
            content=ft.Text(
                "选择要处理的模组（资源包与行为包若互相依赖会合并为一个入口；"
                "整理名称时优先使用设置中的目标语言包名）",
                size=14,
                color=ft.Colors.WHITE,
            ),
            gradient=brand_gradient(),
            padding=ft.Padding.symmetric(horizontal=18, vertical=14),
            border_radius=12,
        )

        tools = ft.Row(
            controls=[
                ft.FilledButton("刷新模组列表", icon=ft.Icons.REFRESH, on_click=lambda e: self.reload_mods()),
                ft.OutlinedButton(
                    "自动整理模组名称",
                    icon=ft.Icons.DRIVE_FILE_RENAME_OUTLINE,
                    on_click=lambda e: self._organize_pack_names(),
                ),
                self.count_label,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Column(
            controls=[
                hero,
                tools,
                ft.Container(content=self.list_view, expand=True),
                ft.Text(
                    "右上角「设置」可配置 AI 接口；进入工具箱后可返回重新选模组。",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=14,
            expand=True,
        )

    def reload_mods(self) -> None:
        self.list_view.controls.clear()
        base = get_minecraft_base_dir()
        if not base.exists():
            self.count_label.value = "未找到 Minecraft 路径"
            self.count_label.color = ft.Colors.ERROR
            self.list_view.controls.append(
                ft.Text(f"未找到目录:\n{base}", color=ft.Colors.ERROR)
            )
            self.list_view.update()
            self.count_label.update()
            return
        try:
            target = (self.config.get("target_language") or "zh_CN").strip() or "zh_CN"
            self._mods = list_mods(base, target_code=target)
        except OSError as exc:
            self.count_label.value = f"扫描失败: {exc}"
            self.count_label.color = ft.Colors.ERROR
            self.count_label.update()
            return

        self.count_label.value = f"共 {len(self._mods)} 个模组"
        self.count_label.color = None
        if not self._mods:
            self.list_view.controls.append(ft.Text("未扫描到模组包", color=ft.Colors.ON_SURFACE_VARIANT))
        else:
            for mod in self._mods:
                self.list_view.controls.append(self._mod_card(mod))
        self.list_view.update()
        self.count_label.update()

    def _mod_card(self, mod: ModEntry) -> ft.Control:
        badges = []
        if mod.has_rp:
            badges.append(
                ft.Container(
                    content=ft.Text("RP", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.PRIMARY,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    border_radius=6,
                )
            )
        if mod.has_bp:
            badges.append(
                ft.Container(
                    content=ft.Text("BP", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.SECONDARY,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    border_radius=6,
                )
            )

        detail_parts = []
        if mod.has_rp:
            detail_parts.append(f"RP: {mod.resource_pack.name}")
        if mod.has_bp:
            detail_parts.append(f"BP: {mod.behavior_pack.name}")
        detail = "  |  ".join(detail_parts)

        return ft.Card(
            content=ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        *badges,
                                        ft.Text(mod.name, weight=ft.FontWeight.W_600, size=15, expand=True),
                                    ],
                                    spacing=8,
                                ),
                                ft.Text(detail, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=14,
                ink=True,
                on_click=lambda e, m=mod: self._enter_mod(m),
            ),
            elevation=0,
            variant=ft.CardVariant.OUTLINED,
        )

    def _enter_mod(self, mod: ModEntry) -> None:
        rp = str(mod.resource_pack) if mod.resource_pack else ""
        bp = str(mod.behavior_pack) if mod.behavior_pack else ""
        self.config.set(rp, "resource_pack_path")
        self.config.set(bp, "behavior_pack_path")
        self.config.set(mod.name, "current_mod_name")
        self.config.save()
        self.on_enter()

    def _organize_pack_names(self) -> None:
        base = get_minecraft_base_dir()
        if not base.exists():
            error_toast(self.page, f"未找到 Minecraft 路径:\n{base}")
            return
        try:
            target = (self.config.get("target_language") or "zh_CN").strip() or "zh_CN"
            plans = plan_pack_renames(base, target_code=target)
        except OSError as exc:
            error_toast(self.page, f"扫描失败: {exc}")
            return
        changes = [p for p in plans if p.changed]
        skipped = [p for p in plans if p.skipped]
        if not changes:
            msg = "没有需要重命名的模组文件夹。"
            if skipped:
                msg += f"\n（跳过 {len(skipped)} 个：无名称或无法解析）"
            toast(self.page, msg)
            return

        preview = "\n".join(
            f"[{p.suffix}] {p.src.parent.name}\\{p.src.name}\n  → {p.dest.name}"
            for p in changes
        )
        confirm(
            self.page,
            title="预览：自动整理模组名称",
            message="",
            yes_text="确认重命名",
            content=ft.Column(
                controls=[
                    ft.Text(
                        f"将重命名 {len(changes)} 个文件夹（跳过 {len(skipped)} 个）。"
                        "优先使用设置中的目标语言包名；行为包加 BP，资源包加 RP。"
                    ),
                    ft.Container(
                        content=ft.Text(preview, font_family="Consolas", size=12, selectable=True),
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        padding=10,
                        height=280,
                    ),
                ],
                tight=True,
                spacing=10,
                width=560,
            ),
            on_yes=lambda: self._apply_renames(changes),
        )

    def _apply_renames(self, changes) -> None:
        ok, errors = apply_pack_renames(changes)
        summary = f"已重命名 {ok} 个文件夹。"
        if errors:
            summary += f"\n失败 {len(errors)} 个，例如:\n" + "\n".join(errors[:8])
            error_toast(self.page, summary)
        else:
            toast(self.page, summary)
        self.reload_mods()
