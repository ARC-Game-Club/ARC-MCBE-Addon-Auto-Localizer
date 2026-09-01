#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弧光自动本地化工具 v1.3.0 —— 启动入口。

实际实现按功能拆分在 utils 包中：
  utils/            纯逻辑模块（模组配对、语言、LLM、实体、格式化等）
  utils/fletui/     Flet 首屏选模组 + 工具箱

配置目录：%APPDATA%/ARCStudio/弧光自动本地化工具/

运行：
  .venv/Scripts/python.exe mcbe_localization_hub.py
"""
import flet as ft

from utils.fletui.app import main


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
