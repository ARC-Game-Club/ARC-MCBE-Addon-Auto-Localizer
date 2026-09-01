# -*- coding: utf-8 -*-
"""可复用 Flet 控件：日志面板、卡片、确认框、提示条。"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

import flet as ft

from ..session_log import session_log_path, write as session_log_write


class LogPanel(ft.Container):
    """底部固定高度的滚动日志，最多保留 max_lines 条。"""

    DEFAULT_HEIGHT = 200

    def __init__(
        self,
        page: ft.Page | None = None,
        max_lines: int = 500,
        height: float | None = None,
        expand: bool = False,
    ):
        self._page = page
        self._max_lines = max_lines
        self._list = ft.ListView(expand=True, auto_scroll=True, spacing=2, padding=8)
        # 默认固定高度贴底；只有显式 expand=True 时才吃剩余空间
        use_expand = expand and height is None
        header = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            "运行日志",
                            size=12,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "已同步到 latest_session.log（每次启动覆盖）",
                            size=10,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            tooltip=str(session_log_path()),
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
                ft.TextButton(
                    "一键复制",
                    icon=ft.Icons.CONTENT_COPY,
                    tooltip="复制全部日志到剪贴板",
                    on_click=self._on_copy,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=0),
                        visual_density=ft.VisualDensity.COMPACT,
                    ),
                ),
            ],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        super().__init__(
            content=ft.Column(
                controls=[
                    header,
                    ft.Container(
                        content=self._list,
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                        expand=True,
                    ),
                ],
                spacing=6,
                expand=use_expand,
                tight=not use_expand,
            ),
            expand=use_expand,
            height=None if use_expand else (height or self.DEFAULT_HEIGHT),
        )

    def get_text(self) -> str:
        lines = []
        for c in self._list.controls:
            if isinstance(c, ft.Text) and c.value:
                lines.append(c.value)
        return "\n".join(lines)

    async def _on_copy(self, _e=None) -> None:
        text = self.get_text()
        if not text.strip():
            if self._page is not None:
                toast(self._page, "日志为空")
            return
        try:
            await ft.Clipboard().set(text)
            if self._page is not None:
                toast(self._page, "日志已复制到剪贴板")
        except Exception as ex:
            if self._page is not None:
                error_toast(self._page, f"复制失败: {ex}")

    def append(self, message: str, *, persist: bool = True) -> None:
        if persist:
            session_log_write(message)
        ts = datetime.now().strftime("%H:%M:%S")
        self._list.controls.append(
            ft.Text(
                f"[{ts}] {message}",
                size=12,
                font_family="Consolas",
                selectable=True,
            )
        )
        overflow = len(self._list.controls) - self._max_lines
        if overflow > 0:
            del self._list.controls[:overflow]
        self._list.update()

    def clear(self) -> None:
        self._list.controls.clear()
        self._list.update()


def SectionCard(
    title: str,
    *controls: ft.Control,
    expand: bool = False,
) -> ft.Card:
    """带标题的内容卡片。"""
    body = ft.Column(
        controls=[
            ft.Text(title, weight=ft.FontWeight.BOLD, size=14),
            *controls,
        ],
        spacing=10,
        tight=True,
        expand=expand,
    )
    return ft.Card(
        content=ft.Container(content=body, padding=16),
        elevation=0,
        variant=ft.CardVariant.OUTLINED,
    )


def toast(page: ft.Page, message: str, action_label: str | None = None, on_action=None) -> None:
    """普通提示条（SnackBar 在 0.86 继承 DialogControl）。"""
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(message),
            action=action_label,
            on_action=on_action,
            # 有 action 时 Flet 默认 persist=True，会一直挡住界面
            persist=False,
            show_close_icon=True,
            duration=ft.Duration(seconds=6),
        )
    )


def error_toast(page: ft.Page, message: str) -> None:
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.ERROR,
            persist=False,
            show_close_icon=True,
            duration=ft.Duration(seconds=8),
        )
    )


def confirm(
    page: ft.Page,
    title: str,
    message: str,
    on_yes: Callable[[], None],
    yes_text: str = "确认",
    no_text: str = "取消",
    content: ft.Control | None = None,
) -> None:
    """回调式确认对话框。"""

    def close(_=None):
        page.pop_dialog()

    def yes(_=None):
        page.pop_dialog()
        on_yes()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=content or ft.Text(message),
        actions=[
            ft.TextButton(no_text, on_click=close),
            ft.FilledButton(yes_text, on_click=yes),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
