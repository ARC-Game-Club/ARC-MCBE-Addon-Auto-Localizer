# -*- coding: utf-8 -*-
"""Minecraft 安装路径与资源包 / 行为包目录检测。"""
import os
from pathlib import Path

# 用户级应用数据：%APPDATA%/ARCStudio/弧光自动汉化工具
APP_VENDOR = "ARCStudio"
APP_NAME = "弧光自动汉化工具"


def get_app_data_dir() -> Path:
    """获取本工具的用户数据目录（配置等，不放仓库里）。"""
    roaming = os.getenv("APPDATA")
    if roaming:
        base = Path(roaming)
    else:
        base = Path(os.getenv("USERPROFILE") or os.path.expanduser("~")) / "AppData" / "Roaming"
    path = base / APP_VENDOR / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_minecraft_base_dir() -> Path:
    """获取 Minecraft Bedrock com.mojang 目录。"""
    user_profile = os.getenv("USERPROFILE") or os.path.expanduser("~")
    return (
        Path(user_profile)
        / "AppData" / "Roaming" / "Minecraft Bedrock"
        / "Users" / "Shared" / "games" / "com.mojang"
    )


def get_behavior_packs_path() -> Path:
    """获取 Minecraft Bedrock behavior_packs 目录路径。"""
    return get_minecraft_base_dir() / "behavior_packs"


def get_pack_root_dirs():
    """返回 (resource_packs_dir, behavior_packs_dir)。"""
    base = get_minecraft_base_dir()
    rp = base / "resource_packs" if base.exists() else None
    return rp, get_behavior_packs_path()


def list_pack_subdirs(packs_dir):
    """列出目录下所有子文件夹名。"""
    if not packs_dir or not Path(packs_dir).is_dir():
        return []
    return sorted(p.name for p in Path(packs_dir).iterdir() if p.is_dir())
