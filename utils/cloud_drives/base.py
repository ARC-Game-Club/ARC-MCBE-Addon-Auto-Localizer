# -*- coding: utf-8 -*-
"""网盘插件基类。

新增网盘：在本目录新建模块，继承 CloudDrive，填 id / display_name，
实现 is_authorized / upload，能分享再实现 share，最后用 @register 注册。
设置页与导出页会按注册表自动出现，不必改 UI。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, ClassVar, Literal

LogFn = Callable[[str], None] | None
AuthMode = Literal["oauth_code", "cookie", "none"]
FieldKind = Literal["text", "password"]

_REGISTRY: dict[str, type["CloudDrive"]] = {}


def register(cls: type["CloudDrive"]) -> type["CloudDrive"]:
    if not getattr(cls, "id", ""):
        raise ValueError(f"{cls.__name__} 必须设置 id")
    _REGISTRY[cls.id] = cls
    return cls


def registered_classes() -> list[type["CloudDrive"]]:
    return list(_REGISTRY.values())


class CloudDriveError(Exception):
    pass


@dataclass(frozen=True)
class ConfigField:
    """设置页自动渲染的配置项（不含 enabled，enabled 每家都有）。"""

    key: str
    label: str
    kind: FieldKind = "text"
    hint: str = ""


@dataclass
class UploadResult:
    remote_id: str
    remote_label: str
    extra: dict = field(default_factory=dict)


@dataclass
class ShareResult:
    url: str
    password: str = ""


@dataclass
class PublishResult:
    driver_id: str
    driver_name: str
    uploaded: UploadResult | None = None
    share: ShareResult | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.uploaded is not None

    def summary(self) -> str:
        if self.error:
            return f"{self.driver_name}失败: {self.error}"
        parts = [self.driver_name, self.uploaded.remote_label if self.uploaded else ""]
        if self.share and self.share.url:
            extra = self.share.url
            if self.share.password:
                extra += f"  提取码 {self.share.password}"
            parts.append(extra)
        return " · ".join(p for p in parts if p)


class CloudDrive(ABC):
    id: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    supports_share: ClassVar[bool] = False
    auth_mode: ClassVar[AuthMode] = "none"
    notes: ClassVar[str] = ""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    @classmethod
    def default_config(cls) -> dict:
        return {"enabled": False}

    def config_fields(self) -> list[ConfigField]:
        return []

    def is_enabled(self) -> bool:
        return bool(self.cfg.get("enabled"))

    @abstractmethod
    def is_authorized(self) -> bool:
        """凭证是否足够发起上传（不必真的打网络）。"""

    def status_text(self) -> str:
        state = "已就绪" if self.is_authorized() else "未就绪"
        return f"{state} · {self.display_name}"

    def authorize_url(self) -> str:
        raise CloudDriveError(f"{self.display_name} 不使用授权码登录")

    def exchange_code(self, code: str) -> None:
        raise CloudDriveError(f"{self.display_name} 不使用授权码登录")

    def test_connection(self) -> str:
        """探测账号，成功返回显示名。"""
        raise CloudDriveError(f"{self.display_name} 未实现连接测试")

    @abstractmethod
    def upload(self, local_path: Path, log: LogFn = None) -> UploadResult:
        """上传本地文件。失败抛 CloudDriveError。"""

    def share(self, uploaded: UploadResult, log: LogFn = None) -> ShareResult:
        raise CloudDriveError(f"{self.display_name} 不支持自动分享")

    def publish(self, local_path: Path, log: LogFn = None) -> PublishResult:
        """上传；若 supports_share 再创建分享。单家失败不抛给调用方。"""
        try:
            uploaded = self.upload(Path(local_path), log=log)
            shared = self.share(uploaded, log=log) if self.supports_share else None
            return PublishResult(self.id, self.display_name, uploaded, shared)
        except CloudDriveError as err:
            return PublishResult(self.id, self.display_name, error=str(err))
        except Exception as err:
            return PublishResult(self.id, self.display_name, error=str(err))


def apply_defaults(root: dict) -> None:
    """把各插件 default_config 补进 root['cloud_drives']。"""
    drives = root.setdefault("cloud_drives", {})
    if not isinstance(drives, dict):
        drives = {}
        root["cloud_drives"] = drives
    for cls in registered_classes():
        cur = drives.get(cls.id)
        if not isinstance(cur, dict):
            drives[cls.id] = dict(cls.default_config())
            continue
        for key, value in cls.default_config().items():
            cur.setdefault(key, value)


def drivers_from(root: dict) -> list[CloudDrive]:
    apply_defaults(root)
    drives = root["cloud_drives"]
    return [cls(drives[cls.id]) for cls in registered_classes()]
