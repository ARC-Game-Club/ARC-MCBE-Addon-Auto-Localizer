# -*- coding: utf-8 -*-
"""网盘插件包。

添加新网盘：
1. 本目录新建 xxx.py，@register class XxxDrive(CloudDrive)
2. 在下面补一行 import，设置页 / 导出页会自动出现
"""
from .base import (
    CloudDrive,
    CloudDriveError,
    ConfigField,
    PublishResult,
    ShareResult,
    UploadResult,
    apply_defaults,
    drivers_from,
    register,
    registered_classes,
)
from . import baidu as _baidu  # noqa: F401
from . import quark as _quark  # noqa: F401

__all__ = [
    "CloudDrive",
    "CloudDriveError",
    "ConfigField",
    "PublishResult",
    "ShareResult",
    "UploadResult",
    "apply_defaults",
    "drivers_from",
    "register",
    "registered_classes",
]
