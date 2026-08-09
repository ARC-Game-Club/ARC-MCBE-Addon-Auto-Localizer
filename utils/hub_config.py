# -*- coding: utf-8 -*-
"""全局配置管理：读取、写入并深度合并默认值。

配置存放在用户 AppData（%APPDATA%/ARCStudio/弧光自动汉化工具），
不写入仓库，避免 API Key 等敏感信息被提交。
"""
import copy
import json
import shutil
from pathlib import Path

from . import PROJECT_ROOT
from .paths import get_app_data_dir

CONFIG_FILE = get_app_data_dir() / "config.json"
# 旧版曾把配置放在仓库根目录，启动时若发现则迁走并删除
_LEGACY_CONFIG_FILE = PROJECT_ROOT / "mcbe_hub_config.json"

DEFAULT_CONFIG = {
    "resource_pack_path": "",
    "behavior_pack_path": "",
    "current_mod_name": "",
    "translator_credit": "DEVILENMO",
    "export_dir": "",
    "text_llm": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "proxy": "127.0.0.1:7890",
    },
    "image_llm": {
        "base_url": "https://api.poe.com/v1",
        "api_key": "",
        "model": "nano-banana-2-lite",
        "proxy": "127.0.0.1:7890",
    },
}


def _migrate_legacy_config(dest: Path) -> None:
    """把仓库根目录的旧配置迁到 AppData，成功后删除旧文件。"""
    if dest.exists() or not _LEGACY_CONFIG_FILE.is_file():
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_LEGACY_CONFIG_FILE, dest)
        _LEGACY_CONFIG_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class HubConfig:
    """配置文件读写，支持深度合并默认值。"""

    def __init__(self, path=None):
        self.path = Path(path) if path else CONFIG_FILE
        _migrate_legacy_config(self.path)
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self._deep_update(self._data, saved)
        except (json.JSONDecodeError, OSError):
            pass
        if not str(self._data.get("translator_credit") or "").strip():
            self._data["translator_credit"] = "DEVILENMO"

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def get(self, *keys):
        d = self._data
        for k in keys:
            d = d[k]
        return d

    def set(self, value, *keys):
        d = self._data
        for k in keys[:-1]:
            d = d[k]
        d[keys[-1]] = value

    @staticmethod
    def _deep_update(base, override):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                HubConfig._deep_update(base[k], v)
            else:
                base[k] = v
