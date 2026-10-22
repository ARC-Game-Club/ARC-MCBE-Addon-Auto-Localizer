#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发布构建脚本（带防呆闸，产物直接可用于 GitHub Release）。

背景：v1.3.3 曾在缺少 flet 的环境里直接用 spec 打包，PyInstaller 对解析不到的
import 只写 warn 不报错，产出了双击即报 No module named 'flet' 的坏 exe。
本脚本在三个环节拦截这类问题：

  闸 1  构建前：当前解释器必须能导入关键依赖（flet、OCR、LLM 等）
  闸 2  构建后：解析 PyInstaller 的 warn 文件，关键模块缺失即失败
  闸 3  打包后：冒烟启动 exe，确认主窗口正常拉起

用法（项目根目录）：
  .venv\\Scripts\\python.exe scripts\\build_release.py

产物：dist/ARC-MCBE-Addon-Auto-Localizer-v<版本>-windows-x64.exe
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "mcbe_localization_hub.spec"
BUILD_DIR = ROOT / "build" / "mcbe_localization_hub"
WARN_FILE = BUILD_DIR / "warn-mcbe_localization_hub.txt"
APP_TITLE = "弧光自动本地化工具"
PROCESS_NAME = "mcbe_localization_hub"
SMOKE_TIMEOUT_S = 150  # onefile 包自解压较慢，留足时间
MIN_SIZE_MB = 150  # 粗防呆下限：v1.3.3 坏包（缺 flet）为 135MB，正常包 ≥190MB
CRITICAL_MODULES = [
    "flet", "openai", "httpx", "numpy", "rapidocr", "onnxruntime",
    "PIL", "requests", "yaml", "qrcode",
]


def fail(msg: str) -> None:
    print(f"\n[build_release] 失败：{msg}", file=sys.stderr)
    sys.exit(1)


def gate_imports() -> None:
    missing = [m for m in CRITICAL_MODULES if importlib.util.find_spec(m) is None]
    if missing:
        fail(
            f"闸 1 未通过：当前解释器缺少依赖 {missing}。请确认用的是项目 .venv，"
            "并执行 .venv\\Scripts\\python.exe -m pip install -r requirements.txt。"
        )
    print(f"[build_release] 闸 1 通过：关键依赖均可导入（{len(CRITICAL_MODULES)} 项）")


def run_pyinstaller() -> None:
    shutil.rmtree(BUILD_DIR, ignore_errors=True)  # 清掉旧 warn，避免读到上次构建的结果
    print("[build_release] 运行 PyInstaller（可能需要数分钟）...")
    proc = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC)],
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        fail(f"闸 2 前置未通过：PyInstaller 退出码 {proc.returncode}")


def gate_warn_file() -> None:
    if not WARN_FILE.exists():
        fail(f"闸 2 未通过：找不到 warn 文件 {WARN_FILE}")
    # 只拦截“整个关键包缺失”（v1.3.3 的 flet 就是这种）；带点号的子模块
    # missing 多为 numpy._core.* 这类运行期惰性导入噪音，包本体已收集，不算失败。
    fatal, noisy = [], 0
    for line in WARN_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"missing module named ([\w.]+)", line.strip())
        if not m or m.group(1).split(".")[0] not in CRITICAL_MODULES:
            continue
        if "." in m.group(1):
            noisy += 1
        else:
            fatal.append(line.strip())
    if fatal:
        fail("闸 2 未通过：warn 文件显示关键模块未打进包：\n  " + "\n  ".join(fatal))
    print(f"[build_release] 闸 2 通过：关键模块完整（{noisy} 条子模块惰性导入警告，属正常噪音）")


def app_window_present() -> bool:
    # 只让 PowerShell 回 ASCII 标记：回传中文标题会撞上控制台编码（GBK/UTF-8）问题
    cmd = (
        "if (Get-Process | Where-Object { $_.MainWindowTitle -like "
        f"'*{APP_TITLE}*' }}) {{ 'FOUND' }} else {{ '' }}"
    )
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, errors="replace",
    )
    return "FOUND" in (ps.stdout or "")


def gate_smoke() -> None:
    exe = ROOT / "dist" / f"{PROCESS_NAME}.exe"
    if not exe.exists():
        fail(f"闸 3 未通过：产物不存在 {exe}")
    print(f"[build_release] 闸 3：冒烟启动 exe（最多等 {SMOKE_TIMEOUT_S} 秒）...")
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    deadline = time.time() + SMOKE_TIMEOUT_S
    try:
        while time.time() < deadline:
            time.sleep(3)
            if proc.poll() is not None:
                fail(f"闸 3 未通过：exe 启动后即退出，退出码 {proc.returncode}")
            if app_window_present():
                print("[build_release] 闸 3 通过：主窗口已拉起")
                return
        fail(f"闸 3 未通过：{SMOKE_TIMEOUT_S} 秒内未见主窗口")
    finally:
        subprocess.run(["taskkill", "/IM", f"{PROCESS_NAME}.exe", "/T", "/F"],
                       capture_output=True)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{APP_TITLE}*' }} "
             "| Stop-Process -Force"],
            capture_output=True, text=True, errors="replace",
        )


def publish_artifact() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    src = ROOT / "dist" / f"{PROCESS_NAME}.exe"
    dst = ROOT / "dist" / f"ARC-MCBE-Addon-Auto-Localizer-v{version}-windows-x64.exe"
    shutil.copyfile(src, dst)
    digest = hashlib.sha256(dst.read_bytes()).hexdigest()
    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"[build_release] 产物：{dst}")
    print(f"[build_release] 大小：{size_mb:.1f} MB   sha256：{digest}")
    if size_mb < MIN_SIZE_MB:
        fail(f"产物仅 {size_mb:.0f} MB（正常约 190-400 MB），疑似缺 flet 桌面运行时或 OCR 模型。")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    gate_imports()
    run_pyinstaller()
    gate_warn_file()
    gate_smoke()
    publish_artifact()
    print("[build_release] 全部通过。")


if __name__ == "__main__":
    main()
