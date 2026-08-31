# -*- coding: utf-8 -*-
"""JSON / JS 批量格式化服务。"""
from __future__ import annotations

from pathlib import Path

from ui.format_json import SKIP, format_json_file

# 扫描时跳过的目录名（备份、依赖等，不是 Addon 正文）
_SKIP_DIR_NAMES = frozenset({"_backup", ".git", "node_modules", "__pycache__"})


def _rel(root: Path, fp: Path) -> str:
    try:
        return str(fp.relative_to(root))
    except ValueError:
        return str(fp)


def _should_skip_path(fp: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in fp.parts)


def _collect(root: Path, pattern: str, log=None, label: str = ""):
    """扫描文件列表；失败返回 None。"""
    root = Path(root)
    kind = label or pattern
    if log:
        log(f"  扫描 {kind} …")
    try:
        files = sorted(
            fp for fp in root.rglob(pattern) if not _should_skip_path(fp)
        )
    except Exception as e:
        if log:
            log(f"  扫描 {kind} 失败: {e}")
        return None
    if log:
        log(f"  找到 {len(files)} 个 {kind}")
    return files


def _tally(result, ok: int, fail: int, skip: int) -> tuple[int, int, int]:
    if result is SKIP:
        return ok, fail, skip + 1
    if result:
        return ok + 1, fail, skip
    return ok, fail + 1, skip


def format_json_files_in(
    root: Path,
    indent: int = 4,
    log=None,
    on_progress=None,
    files=None,
    progress_offset: int = 0,
    progress_total: int | None = None,
):
    """
    递归格式化目录下所有 .json，返回 (成功数, 失败数, 跳过数)。

    on_progress(done, total, rel_path)：done/total 为全局进度（含 offset）。
    files: 若已预扫描可传入，避免重复 rglob。
    """
    root = Path(root)
    if files is None:
        files = _collect(root, "*.json", log=log, label="JSON")
        if files is None:
            return 0, 1, 0
    total = progress_total if progress_total is not None else len(files)
    ok = fail = skip = 0
    for i, fp in enumerate(files):
        rel = _rel(root, fp)
        if on_progress:
            on_progress(progress_offset + i, total, rel)
        try:
            ok, fail, skip = _tally(
                format_json_file(str(fp), indent=indent, quiet=True, log=log),
                ok,
                fail,
                skip,
            )
        except Exception as e:
            fail += 1
            if log:
                log(f"  异常: {rel} ({e})")
        if on_progress:
            on_progress(progress_offset + i + 1, total, rel)
    return ok, fail, skip


def format_js_files_in(
    root: Path,
    log=None,
    on_progress=None,
    files=None,
    progress_offset: int = 0,
    progress_total: int | None = None,
):
    """
    递归格式化目录下所有 .js，返回 (成功数, 失败数, 跳过数)。

    on_progress / files / progress_* 同 format_json_files_in。
    """
    try:
        from ui.format_js import format_js_file
    except Exception as e:
        if log:
            log(f"加载 JS 格式化器失败: {e}")
        return 0, 0, 0

    root = Path(root)
    if files is None:
        files = _collect(root, "*.js", log=log, label="JS")
        if files is None:
            return 0, 1, 0
    total = progress_total if progress_total is not None else len(files)
    ok = fail = skip = 0
    for i, fp in enumerate(files):
        rel = _rel(root, fp)
        if on_progress:
            on_progress(progress_offset + i, total, rel)
        try:
            ok, fail, skip = _tally(
                format_js_file(str(fp), quiet=True, log=log),
                ok,
                fail,
                skip,
            )
        except Exception as e:
            fail += 1
            if log:
                log(f"  异常: {rel} ({e})")
        if on_progress:
            on_progress(progress_offset + i + 1, total, rel)
    return ok, fail, skip


def collect_format_targets(root: Path, log=None):
    """
    预扫描包内 JSON/JS，返回 (json_files, js_files)。
    任一侧扫描失败则抛出 RuntimeError。
    """
    root = Path(root)
    jsons = _collect(root, "*.json", log=log, label="JSON")
    jss = _collect(root, "*.js", log=log, label="JS")
    if jsons is None or jss is None:
        raise RuntimeError(f"扫描包内文件失败: {root}")
    return jsons, jss
