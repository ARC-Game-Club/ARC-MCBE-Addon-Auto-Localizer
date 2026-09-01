# -*- coding: utf-8 -*-
"""会话日志：每次启动覆盖写入 AppData，仅保留最近一份。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from threading import Lock

from .paths import get_app_data_dir

SESSION_LOG_NAME = "latest_session.log"
_lock = Lock()
_started = False


def session_log_path() -> Path:
    return get_app_data_dir() / SESSION_LOG_NAME


def start_session() -> Path:
    """新会话开始时覆盖旧日志。"""
    global _started
    path = session_log_path()
    header = (
        "=== 弧光自动本地化工具 / ARC Auto Localizer ===\n"
        f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Python: {sys.version.split()[0]}\n"
        f"日志路径: {path}\n"
        "=" * 50 + "\n\n"
    )
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header, encoding="utf-8")
        _started = True
    return path


def write(message: str) -> None:
    """追加一行到会话日志（线程安全）。"""
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n"
    with _lock:
        if not _started:
            start_session()
        try:
            with open(session_log_path(), "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass
