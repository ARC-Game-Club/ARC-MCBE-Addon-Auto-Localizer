# -*- coding: utf-8 -*-
"""MCBE 汉化工具中心 —— 工具函数包。

包含纯逻辑模块（路径、配置、语言文件、LLM 调用等）与 Flet 界面（fletui 子包）。
"""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller 打包后：配置与输出文件写到 exe 所在目录（onefile 的 __file__ 在临时解压目录，不可写）
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
