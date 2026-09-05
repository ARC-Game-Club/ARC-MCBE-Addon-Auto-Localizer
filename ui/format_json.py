#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON 格式化脚本
用于重新格式化 JSON 文件，统一缩进与排版

约束：
- 跳过 manifest.json（UUID 等包标识，格式化步骤不应改它）
- 原文件若是单行 minify，保持 minify，不膨胀体积
- 不在包内留下旁路 *.backup（MC 会误加载）
"""

import json
import os
import sys
import tempfile
from pathlib import Path

from utils.json_io import loads_jsonc

SKIP = "skip"

# 步骤 0 规范化时跳过；manifest 的语义改动走 manifest_service
_SKIP_BASENAMES = frozenset({"manifest.json"})


def _atomic_write(path: str, content: str) -> None:
    path = str(path)
    directory = str(Path(path).parent)
    fd, tmp = tempfile.mkstemp(prefix=".fmt_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_minified_json(content: str) -> bool:
    """原文件基本是单行 minify（允许末尾换行）。"""
    body = content.lstrip("\ufeff").strip()
    if not body:
        return False
    return "\n" not in body and "\r" not in body


def format_json_file(input_path, output_path=None, indent=4, quiet=True, log=None):
    """
    格式化 JSON 文件。

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径，如果为 None 则覆盖原文件
        indent: 缩进空格数
        quiet: True 时不刷屏打印（批量规范化默认）
        log: 可选回调；出错时优先写入日志（便于 UI 显示）
    """
    def _p(msg):
        if not quiet:
            print(msg)

    def _err(msg):
        if log:
            log(msg)
        else:
            print(msg)

    def _skip(msg):
        if log:
            log(msg)

    name = Path(input_path).name
    if name.endswith(".backup") or name.endswith(".bak"):
        _skip(f"  跳过: {name}（备份文件）")
        return SKIP
    if name.lower() in _SKIP_BASENAMES:
        _skip(f"  跳过: {name}（包标识，不在规范化步骤改写）")
        return SKIP

    _p(f"正在读取文件: {input_path}")

    try:
        with open(input_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except UnicodeDecodeError:
        _skip(
            f"  跳过: {name}（非 UTF-8 文本，可能是 marketplace 缓存/二进制文件）"
        )
        return SKIP
    except OSError as e:
        _err(f"读取失败: {input_path} ({e})")
        return False

    _p(f"文件大小: {len(content)} 字符")
    _p("正在解析并格式化...")

    stripped = content.lstrip("\ufeff").lstrip()
    if not stripped:
        _skip(f"  跳过: {name}（空文件）")
        return SKIP
    if stripped[0] not in "{[":
        _skip(f"  跳过: {name}（非明文 JSON，可能是 marketplace 加密/缓存）")
        return SKIP

    # 原包 minify → 保持 minify，避免 textures_list 等体积暴涨
    if _is_minified_json(content):
        _skip(f"  跳过: {name}（原为 minify，保持单行）")
        return SKIP

    try:
        # MCBE 包常含 // 或 /* */ 注释（JSONC）；严格 json.loads 会失败
        data = loads_jsonc(content)
    except json.JSONDecodeError as e:
        if e.pos == 0:
            _skip(f"  跳过: {name}（非明文 JSON，可能是 marketplace 加密/缓存）")
            return SKIP
        _err(f"JSON 解析失败: {input_path} ({e})")
        return False

    try:
        formatted = json.dumps(
            data,
            ensure_ascii=False,
            indent=indent,
            sort_keys=False,
        )
        if not formatted.endswith("\n"):
            formatted += "\n"
    except (TypeError, ValueError) as e:
        _err(f"序列化失败: {input_path} ({e})")
        return False

    # 内容无变化：不写盘
    if formatted == content:
        _p("内容已是规范格式，跳过")
        return True

    if output_path is None:
        output_path = input_path

    _p(f"正在写入文件: {output_path}")
    try:
        _atomic_write(output_path, formatted)
    except Exception as e:
        _err(f"写入失败: {output_path} ({e})")
        return False

    _p("格式化完成！")
    _p(f"原始大小: {len(content)} 字符")
    _p(f"格式化后大小: {len(formatted)} 字符")

    return True


def main():
    """主函数"""
    default_input = r"C:\Users\DEVILENMO\AppData\Roaming\Minecraft Bedrock\Users\Shared\games\com.mojang\development_behavior_packs\MORPH Add-On BP\scripts\main.json"

    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        input_path = default_input

    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    else:
        output_path = None

    if not os.path.exists(input_path):
        print(f"错误: 文件不存在: {input_path}")
        sys.exit(1)

    success = format_json_file(input_path, output_path, quiet=False)

    if success:
        print("\n格式化成功完成！")
        sys.exit(0)
    else:
        print("\n格式化失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
