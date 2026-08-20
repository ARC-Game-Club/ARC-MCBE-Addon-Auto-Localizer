# -*- coding: utf-8 -*-
"""弧光自动本地化工具 —— Flet 主窗口装配。

不用 page.views（0.86 下 View 内 expand 易塌成白屏），改为单页内容切换：
  welcome  → 首屏选模组
  toolbox  → NavigationRail 工具箱
  settings → 设置
"""
from __future__ import annotations

import flet as ft

from ..hub_config import HubConfig
from .achievement_tab import AchievementTab
from .entity_tab import EntityTab
from .export_tab import ExportTab
from .image_tab import ImageTab
from .localize_tab import LocalizeTab
from .pbr_tab import PbrTab
from .settings_view import SettingsView
from .theme import APP_TITLE, APP_VERSION, ICON_ASSET, apply_page_theme
from .welcome_view import WelcomeView

NAV_ITEMS = [
    ("localize", "模组本地化", ft.Icons.TRANSLATE),
    ("image", "图片本地化", ft.Icons.IMAGE),
    ("pbr", "灵动视效", ft.Icons.VISIBILITY),
    ("achievement", "成就兼容", ft.Icons.EMOJI_EVENTS),
    ("entity", "实体工具", ft.Icons.PETS),
    ("export", "导出本地化包", ft.Icons.ARCHIVE),
]


class HubApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config = HubConfig()
        self.file_picker = ft.FilePicker()
        page.services.append(self.file_picker)

        self.status_text = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.back_btn = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            tooltip="返回",
            visible=False,
            on_click=lambda e: self._on_back(),
        )
        self._screen = "welcome"
        self._return_screen = "welcome"
        self._nav_index = 0
        self._tabs: dict[str, object] = {}
        self._tabs_pack_key: tuple[str, str] | None = None
        self._welcome: WelcomeView | None = None
        self._body = ft.Container(expand=True, padding=16)

        apply_page_theme(page)
        page.appbar = self._build_appbar()
        page.add(self._body)
        self._show_welcome()

    def _build_appbar(self) -> ft.AppBar:
        return ft.AppBar(
            leading=self.back_btn,
            automatically_imply_leading=False,
            title=ft.Row(
                controls=[
                    ft.Image(src=ICON_ASSET, width=28, height=28, fit=ft.BoxFit.CONTAIN),
                    ft.Text(APP_TITLE, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        f"v{APP_VERSION}",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    self.status_text,
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            center_title=False,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="设置",
                    on_click=lambda e: self._show_settings(),
                )
            ],
        )

    def _update_status(self) -> None:
        name = (self.config.get("current_mod_name") or "").strip()
        rp = self.config.get("resource_pack_path").strip()
        bp = self.config.get("behavior_pack_path").strip()
        if name:
            bits = [name]
            if rp:
                bits.append("有RP")
            if bp:
                bits.append("有BP")
            self.status_text.value = "  ·  " + "  ·  ".join(bits)
        else:
            self.status_text.value = "  ·  请选择模组"
        try:
            self.status_text.update()
        except Exception:
            pass

    def _set_back(self, visible: bool, tooltip: str = "返回") -> None:
        self.back_btn.visible = visible
        self.back_btn.tooltip = tooltip
        try:
            self.back_btn.update()
        except Exception:
            pass

    def _on_back(self) -> None:
        if self._screen == "settings":
            if self._return_screen == "toolbox":
                self._show_toolbox()
            else:
                self._show_welcome()
        else:
            self._show_welcome()

    def _show_welcome(self) -> None:
        self._screen = "welcome"
        self._set_back(False)
        self._welcome = WelcomeView(
            self.page, self.config, on_enter=self._show_toolbox
        )
        self._body.content = self._welcome.root
        self._body.padding = 16
        self._update_status()
        self.page.update()
        self._welcome.reload_mods()

    def _show_toolbox(self) -> None:
        self._screen = "toolbox"
        self._set_back(True, "返回选模组")
        pack_key = (
            self.config.get("resource_pack_path").strip(),
            self.config.get("behavior_pack_path").strip(),
        )
        # 同一模组再次进入工具箱时复用页签，避免重复跑进页自动规范化
        if not self._tabs or self._tabs_pack_key != pack_key:
            self._tabs_pack_key = pack_key

            def on_pack_paths_changed() -> None:
                """本地化后文件夹改名时：同步 pack_key、状态栏，并刷新图片目录列表。"""
                self._tabs_pack_key = (
                    self.config.get("resource_pack_path").strip(),
                    self.config.get("behavior_pack_path").strip(),
                )
                self._update_status()
                image_tab = self._tabs.get("image")
                if image_tab is not None and hasattr(image_tab, "refresh_folders"):
                    try:
                        image_tab.refresh_folders()
                    except Exception:
                        pass

            self._tabs = {
                "localize": LocalizeTab(
                    self.page, self.config, on_pack_paths_changed=on_pack_paths_changed
                ),
                "image": ImageTab(self.page, self.config),
                "pbr": PbrTab(self.page, self.config),
                "achievement": AchievementTab(self.page, self.config),
                "entity": EntityTab(self.page, self.config),
                "export": ExportTab(self.page, self.config, self.file_picker),
            }
        self._nav_index = 0
        content_host = ft.Container(expand=True)
        content_host.content = self._tabs["localize"].root

        def on_nav(e: ft.ControlEvent):
            self._nav_index = e.control.selected_index
            key = NAV_ITEMS[self._nav_index][0]
            content_host.content = self._tabs[key].root
            content_host.update()

        rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=88,
            group_alignment=-0.9,
            destinations=[
                ft.NavigationRailDestination(icon=icon, label=label)
                for _, label, icon in NAV_ITEMS
            ],
            on_change=on_nav,
        )
        self._body.content = ft.Row(
            controls=[rail, ft.VerticalDivider(width=1), content_host],
            expand=True,
            spacing=0,
        )
        self._body.padding = 0
        self._update_status()
        self.page.update()

    def _show_settings(self) -> None:
        self._return_screen = self._screen if self._screen != "settings" else self._return_screen
        self._screen = "settings"
        self._set_back(True, "返回")

        def on_saved() -> None:
            # 目标语言等变更后重建工具箱页签，使步骤文案立即生效
            self._tabs = {}
            self._tabs_pack_key = None
            self._update_status()

        settings = SettingsView(
            self.page, self.config, on_saved=on_saved, file_picker=self.file_picker
        )
        self._body.content = settings.root
        self._body.padding = 16
        self.page.update()


def main(page: ft.Page) -> None:
    HubApp(page)
