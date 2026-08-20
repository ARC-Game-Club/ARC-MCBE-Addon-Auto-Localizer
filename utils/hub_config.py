# -*- coding: utf-8 -*-
"""全局配置管理：读取、写入并深度合并默认值。

配置存放在用户 AppData（%APPDATA%/ARCStudio/弧光自动本地化工具），
不写入仓库，避免 API Key 等敏感信息被提交。
"""
import copy
import json
import shutil
from pathlib import Path

from . import PROJECT_ROOT
from .languages import DEFAULT_CODE
from .paths import get_app_data_dir, get_legacy_app_data_dirs

CONFIG_FILE = get_app_data_dir() / "config.json"
# 旧版曾把配置放在仓库根目录，启动时若发现则迁走并删除
_LEGACY_CONFIG_FILE = PROJECT_ROOT / "mcbe_hub_config.json"

DEFAULT_CONFIG = {
    "resource_pack_path": "",
    "behavior_pack_path": "",
    "current_mod_name": "",
    "mods_base_dir": "",
    "translator_credit": "DEVILENMO",
    "target_language": DEFAULT_CODE,
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
    "cloud_drives": {},
}


def _migrate_legacy_config(dest: Path) -> None:
    """把仓库根目录或旧 AppData 目录的配置迁到新位置。"""
    if dest.exists():
        return
    candidates: list[Path] = []
    if _LEGACY_CONFIG_FILE.is_file():
        candidates.append(_LEGACY_CONFIG_FILE)
    for legacy_dir in get_legacy_app_data_dirs():
        legacy_cfg = legacy_dir / "config.json"
        if legacy_cfg.is_file():
            candidates.append(legacy_cfg)
    if not candidates:
        return
    src = candidates[0]
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if src == _LEGACY_CONFIG_FILE:
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
        code = str(self._data.get("target_language") or "").strip()
        if not code:
            self._data["target_language"] = DEFAULT_CODE
        self._migrate_baidu_pan()
        from .cloud_drives import apply_defaults
        apply_defaults(self._data)

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

    def _migrate_baidu_pan(self) -> None:
        """旧版 baidu_pan 迁到 cloud_drives.baidu。"""
        old = self._data.get("baidu_pan")
        if not isinstance(old, dict):
            return
        drives = self._data.setdefault("cloud_drives", {})
        if not isinstance(drives, dict):
            drives = {}
            self._data["cloud_drives"] = drives
        baidu = drives.setdefault("baidu", {})
        if not isinstance(baidu, dict):
            baidu = {}
            drives["baidu"] = baidu
        for key, value in old.items():
            current = baidu.get(key)
            if key not in baidu or current in ("", 0, None):
                if value not in ("", None):
                    baidu[key] = value
        self._data.pop("baidu_pan", None)

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
