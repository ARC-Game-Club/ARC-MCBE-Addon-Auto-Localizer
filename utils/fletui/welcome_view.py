# -*- coding: utf-8 -*-
"""启动首屏：模组卡片列表。"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from ..mod_catalog import ModEntry, list_mods
from ..pack_manage_service import (
    delete_pack_dirs,
    open_folder,
    prune_config_selection,
)
from ..pack_rename_service import apply_pack_renames, plan_pack_renames
from ..paths import resolve_mods_base_dir
from .components import choose, confirm, error_toast, toast
from .theme import ICON_ASSET, brand_gradient


class WelcomeView:
    """首屏：扫描并选择模组。"""

    def __init__(self, page: ft.Page, config, on_enter, on_mods_changed=None):
        self.page = page
        self.config = config
        self.on_enter = on_enter
        self.on_mods_changed = on_mods_changed
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

    def _mods_base(self):
        return resolve_mods_base_dir(self.config.get("mods_base_dir"))

    def reload_mods(self) -> None:
        self.list_view.controls.clear()
        base = self._mods_base()
        if not base.exists():
            self.count_label.value = "未找到模组目录"
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

    @staticmethod
    def _mod_icon_src(mod: ModEntry) -> str:
        """优先资源包 / 行为包的 pack_icon.png，否则用默认品牌图标。"""
        for pack in mod.pack_paths():
            icon = Path(pack) / "pack_icon.png"
            if icon.is_file():
                return str(icon)
        return ICON_ASSET

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

        icon = ft.Container(
            content=ft.Image(
                src=self._mod_icon_src(mod),
                width=48,
                height=48,
                fit=ft.BoxFit.COVER,
                border_radius=8,
                error_content=ft.Image(
                    src=ICON_ASSET, width=48, height=48, fit=ft.BoxFit.COVER, border_radius=8
                ),
            ),
            width=48,
            height=48,
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Row(
                    controls=[
                        icon,
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
                        ft.IconButton(
                            icon=ft.Icons.FOLDER_OPEN,
                            tooltip="打开模组所在文件夹",
                            on_click=lambda e, m=mod: self._open_mod_folder(m),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip="删除此模组",
                            icon_color=ft.Colors.ERROR,
                            on_click=lambda e, m=mod: self._delete_mod(m),
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.only(left=14, top=6, bottom=6, right=6),
                ink=True,
                on_click=lambda e, m=mod: self._enter_mod(m),
            ),
            elevation=0,
            variant=ft.CardVariant.OUTLINED,
        )

    def _open_mod_folder(self, mod: ModEntry) -> None:
        packs = mod.pack_paths()
        if not packs:
            error_toast(self.page, "该模组没有可打开的包目录")
            return
        if mod.has_rp and mod.has_bp:
            # 双包：让用户选择要打开哪一个
            choose(
                self.page,
                title=f"打开模组文件夹：{mod.name}",
                message="该模组同时包含资源包与行为包，请选择要打开的目录：",
                options=[
                    ("资源包（RP）", lambda: self._open_pack_folder(mod.resource_pack)),
                    ("行为包（BP）", lambda: self._open_pack_folder(mod.behavior_pack)),
                ],
            )
            return
        self._open_pack_folder(packs[0])

    def _open_pack_folder(self, pack: Path | None) -> None:
        if pack is None:
            error_toast(self.page, "该包目录不存在")
            return
        try:
            open_folder(pack)
        except Exception as exc:
            error_toast(self.page, f"打开文件夹失败: {exc}")

    def _delete_mod(self, mod: ModEntry) -> None:
        paths = mod.pack_paths()
        if not paths:
            error_toast(self.page, "该模组没有可删除的包目录")
            return
        preview = "\n".join(f"• {p}" for p in paths)
        confirm(
            self.page,
            title=f"删除模组：{mod.name}",
            message="",
            yes_text="永久删除",
            content=ft.Column(
                controls=[
                    ft.Text(
                        "将从磁盘永久删除以下文件夹（不可恢复，删除前请确认游戏已关闭）：",
                        color=ft.Colors.ERROR,
                    ),
                    ft.Container(
                        content=ft.Text(preview, font_family="Consolas", size=12, selectable=True),
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        padding=10,
                    ),
                ],
                tight=True,
                spacing=10,
                width=560,
            ),
            on_yes=lambda: self._apply_delete(mod, paths),
        )

    def _apply_delete(self, mod: ModEntry, paths: list[Path]) -> None:
        ok, errors = delete_pack_dirs(paths)
        if ok:
            prune_config_selection(self.config, paths)
            if self.on_mods_changed is not None:
                try:
                    self.on_mods_changed()
                except Exception:
                    pass
        if errors:
            error_toast(
                self.page,
                f"已删除 {ok} 个文件夹，失败 {len(errors)} 个（可能被游戏占用）:\n"
                + "\n".join(errors[:8]),
            )
        elif ok:
            toast(self.page, f"已删除模组「{mod.name}」的 {ok} 个文件夹")
        else:
            error_toast(self.page, "没有可删除的文件夹（可能已被删除或移动）")
        self.reload_mods()

    def _enter_mod(self, mod: ModEntry) -> None:
        rp = str(mod.resource_pack) if mod.resource_pack else ""
        bp = str(mod.behavior_pack) if mod.behavior_pack else ""
        self.config.set(rp, "resource_pack_path")
        self.config.set(bp, "behavior_pack_path")
        self.config.set(mod.name, "current_mod_name")
        self.config.save()
        self.on_enter()

    def _organize_pack_names(self) -> None:
        base = self._mods_base()
        if not base.exists():
            error_toast(self.page, f"未找到模组目录:\n{base}")
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
