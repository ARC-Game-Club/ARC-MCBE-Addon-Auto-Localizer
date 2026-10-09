# -*- coding: utf-8 -*-
"""标签页基类：后台任务、日志与进度条。"""
from __future__ import annotations

import threading
import traceback

import flet as ft

from ..session_log import write as session_log_write
from .components import LogPanel, error_toast


class BaseTab:
    """持有 page / config，提供 run_in_thread 与进度更新。"""

    def __init__(self, page: ft.Page, config):
        self.page = page
        self.config = config
        self._stop_flag = threading.Event()
        self._busy = False
        self._busy_lock = threading.Lock()
        self.log_panel: LogPanel | None = None
        self.progress: ft.ProgressBar | None = None
        self.progress_label: ft.Text | None = None
        self.root = ft.Container(expand=True, padding=16)

    def build(self) -> ft.Control:
        raise NotImplementedError

    def log(self, message: str) -> None:
        session_log_write(message)
        if self.log_panel is None:
            return
        try:
            self.log_panel.append(message, persist=False)
        except Exception:
            pass

    def set_working(self, message: str = "处理中…") -> None:
        """长任务等待时显示不确定进度与状态文案。"""
        if self.progress is not None:
            self.progress.value = None
        if self.progress_label is not None:
            self.progress_label.value = message
        try:
            if self.progress is not None:
                self.progress.update()
            if self.progress_label is not None:
                self.progress_label.update()
        except Exception:
            pass

    def clear_working(self) -> None:
        if self.progress is not None and self.progress.value is None:
            self.progress.value = 0
        if self.progress_label is not None:
            self.progress_label.value = ""
        try:
            if self.progress is not None:
                self.progress.update()
            if self.progress_label is not None:
                self.progress_label.update()
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

    def on_busy_changed(self, busy: bool) -> None:
        """子类可覆盖：任务开始/结束时更新按钮禁用态等 UI。"""

    def run_in_thread(self, func, *args, **kwargs) -> bool:
        """启动后台任务。若已有任务在跑则拒绝并提示，避免叠跑改路径导致写失败。"""
        with self._busy_lock:
            if self._busy:
                self.log("已有任务在运行，请等待完成后再试（避免重复点击叠跑）")
                try:
                    error_toast(self.page, "已有任务在运行，请等待完成后再试")
                except Exception:
                    pass
                return False
            self._busy = True
            self._stop_flag.clear()
        self.set_working("运行中…")
        try:
            self.on_busy_changed(True)
        except Exception:
            pass
        self.page.run_thread(self._thread_wrap, func, args, kwargs)
        return True

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
            with self._busy_lock:
                self._busy = False
            try:
                self.on_busy_changed(False)
            except Exception:
                pass
            self.clear_working()

    def make_progress_row(self) -> ft.Control:
        self.progress = ft.ProgressBar(value=0, expand=True)
        self.progress_label = ft.Text("", expand=True, size=12)
        return ft.Row(
            controls=[self.progress, self.progress_label],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def make_log_panel(self, expand: bool = False, height: float | None = None) -> LogPanel:
        """默认固定高度贴在页面底部；需要占满剩余空间时再传 expand=True。"""
        self.log_panel = LogPanel(page=self.page, expand=expand, height=height)
        return self.log_panel