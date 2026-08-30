# -*- coding: utf-8 -*-
"""标签页基类：后台任务、日志与进度条。"""
from __future__ import annotations

import threading
import traceback

import flet as ft

from .components import LogPanel, error_toast


class BaseTab:
    """持有 page / config，提供 run_in_thread 与进度更新。"""

    def __init__(self, page: ft.Page, config):
        self.page = page
        self.config = config
        self._stop_flag = threading.Event()
        self._busy = False
        self.log_panel: LogPanel | None = None
        self.progress: ft.ProgressBar | None = None
        self.progress_label: ft.Text | None = None
        self.root = ft.Container(expand=True, padding=16)

    def build(self) -> ft.Control:
        raise NotImplementedError

    def log(self, message: str) -> None:
        if self.log_panel is None:
            return
        try:
            self.log_panel.append(message)
        except Exception:
            pass

    def set_progress(self, done: int, total: int) -> None:
        if self.progress is None:
            return
        pct = (done / total) if total else 0
        self.progress.value = pct
        if self.progress_label is not None:
            self.progress_label.value = f"{done}/{total}" if total else ""
        try:
            self.progress.update()
            if self.progress_label is not None:
                self.progress_label.update()
        except Exception:
            pass

    def run_in_thread(self, func, *args, **kwargs) -> None:
        self._stop_flag.clear()
        self._busy = True
        self.page.run_thread(self._thread_wrap, func, args, kwargs)

    def _thread_wrap(self, func, args, kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception as e:
            self.log(f"发生错误: {e}\n{traceback.format_exc()}")
            try:
                error_toast(self.page, f"发生错误: {e}")
            except Exception:
                pass
        finally:
            self._busy = False

    def make_progress_row(self) -> ft.Control:
        self.progress = ft.ProgressBar(value=0, expand=True)
        self.progress_label = ft.Text("", width=90, size=12)
        return ft.Row(
            controls=[self.progress, self.progress_label],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def make_log_panel(self, expand: bool = False, height: float | None = None) -> LogPanel:
        """默认固定高度贴在页面底部；需要占满剩余空间时再传 expand=True。"""
        self.log_panel = LogPanel(page=self.page, expand=expand, height=height)
        return self.log_panel