# -*- coding: utf-8 -*-
"""品牌配色与 Material 3 主题。"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from .. import PROJECT_ROOT

APP_TITLE = "弧光自动本地化工具"
APP_VERSION = "1.3.0"
ICON_ASSET = "icon.png"
WINDOW_ICON_FILE = "app_icon.ico"

# 取自 assets/icon.png 实际像素
BRAND_INDIGO = "#24266D"
BRAND_VIOLET = "#5C256E"
BRAND_MAGENTA = "#A7205B"
BRAND_CRIMSON = "#CA1E54"
BRAND_PINK = "#E83467"


def build_theme() -> ft.Theme:
    """以品红为种子色，让 M3 生成完整浅色/深色调色板。"""
    return ft.Theme(
        color_scheme_seed=BRAND_MAGENTA,
        use_material3=True,
        visual_density=ft.VisualDensity.STANDARD,
    )


def brand_gradient() -> ft.LinearGradient:
    """与图标一致：左下靛蓝 → 中部紫 → 右上玫红。"""
    return ft.LinearGradient(
        begin=ft.Alignment(-1, 1),
        end=ft.Alignment(1, -1),
        colors=[BRAND_INDIGO, BRAND_VIOLET, BRAND_CRIMSON],
    )


def resolve_window_icon() -> str | None:
    """窗口标题栏图标需 .ico 绝对路径；打包后在 sys._MEIPASS/assets。"""
    import sys

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / WINDOW_ICON_FILE)
    candidates.extend(
        [
            PROJECT_ROOT / "assets" / WINDOW_ICON_FILE,
            Path.cwd() / "assets" / WINDOW_ICON_FILE,
            Path(__file__).resolve().parent.parent.parent / "assets" / WINDOW_ICON_FILE,
        ]
    )
    for p in candidates:
        try:
            if p.is_file():
                return str(p.resolve())
        except OSError:
            continue
    return None


def apply_page_theme(page: ft.Page) -> None:
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = build_theme()
    page.dark_theme = build_theme()
    page.title = f"{APP_TITLE} v{APP_VERSION}"
    page.window.width = 1060
    page.window.height = 780
    page.window.min_width = 860
    page.window.min_height = 640
    page.padding = 0
    icon = resolve_window_icon()
    if icon:
        page.window.icon = icon
