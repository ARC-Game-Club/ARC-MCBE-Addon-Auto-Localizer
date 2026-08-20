# -*- coding: utf-8 -*-
"""Minecraft 安装路径与资源包 / 行为包目录检测。"""
import os
from pathlib import Path

# 用户级应用数据：%APPDATA%/ARCStudio/弧光自动本地化工具
APP_VENDOR = "ARCStudio"
APP_NAME = "弧光自动本地化工具"
# 旧版产品名（配置迁移用）
LEGACY_APP_NAMES = ("弧光自动汉化工具",)


def _appdata_base() -> Path:
    roaming = os.getenv("APPDATA")
    if roaming:
        return Path(roaming)
    return Path(os.getenv("USERPROFILE") or os.path.expanduser("~")) / "AppData" / "Roaming"


def get_app_data_dir() -> Path:
    """获取本工具的用户数据目录（配置等，不放仓库里）。"""
    path = _appdata_base() / APP_VENDOR / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_legacy_app_data_dirs() -> list[Path]:
    """旧版用户数据目录（用于迁移配置）。"""
    base = _appdata_base() / APP_VENDOR
    return [base / name for name in LEGACY_APP_NAMES]


def get_minecraft_base_dir() -> Path:
    """获取 Minecraft Bedrock 默认 com.mojang 目录。"""
    user_profile = os.getenv("USERPROFILE") or os.path.expanduser("~")
    return (
        Path(user_profile)
        / "AppData" / "Roaming" / "Minecraft Bedrock"
        / "Users" / "Shared" / "games" / "com.mojang"
    )


def resolve_mods_base_dir(custom: str | None = None) -> Path:
    """模组扫描根目录：自定义路径非空则用之，否则默认 com.mojang。"""
    custom = (custom or "").strip()
    if custom:
        return Path(custom).expanduser()
    return get_minecraft_base_dir()


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
