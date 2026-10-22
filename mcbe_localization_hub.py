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
import os
import sys

import flet as ft

from utils.fletui.app import main


if __name__ == "__main__":
    selftest_out = os.environ.get("MCBE_SELFTEST")
    if selftest_out:  # 发布冒烟自检：验证冻结环境 https 能力后写结果文件退出
        import http.client
        import ssl

        ok = hasattr(ssl, "SSLContext") and hasattr(http.client, "HTTPSConnection")
        with open(selftest_out, "w", encoding="utf-8") as f:
            f.write("OK" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    ft.run(main, assets_dir="assets")
