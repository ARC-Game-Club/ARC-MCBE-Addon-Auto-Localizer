# -*- coding: utf-8 -*-
"""JSON / JS 批量格式化服务。"""
from pathlib import Path

from ui.format_json import format_json_file


def format_json_files_in(root: Path, indent: int = 4, log=None):
    """递归格式化目录下所有 .json，返回 (成功数, 失败数)。"""
    ok = fail = 0
    for fp in sorted(Path(root).rglob("*.json")):
        try:
            if format_json_file(str(fp), indent=indent):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            if log:
                log(f"  失败: {fp.name} ({e})")
    return ok, fail


def format_js_files_in(root: Path, log=None):
    """递归格式化目录下所有 .js，返回 (成功数, 失败数)。"""
    try:
        from ui.format_js import format_js_file
    except Exception as e:
        if log:
            log(f"加载 JS 格式化器失败: {e}")
        return 0, 0
    ok = fail = 0
    for fp in sorted(Path(root).rglob("*.js")):
        try:
            if format_js_file(str(fp)):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            if log:
                log(f"  失败: {fp.name} ({e})")
    return ok, fail
