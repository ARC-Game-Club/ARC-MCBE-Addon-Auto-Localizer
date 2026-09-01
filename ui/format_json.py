#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON 格式化脚本
用于重新格式化 JSON 文件，统一缩进与排版
"""

import json
import os
import sys
from pathlib import Path

from utils.json_io import loads_jsonc

SKIP = "skip"


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

    _p(f"正在读取文件: {input_path}")

    try:
        with open(input_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except UnicodeDecodeError:
        name = Path(input_path).name
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
        name = Path(input_path).name
        _skip(f"  跳过: {name}（空文件）")
        return SKIP
    if stripped[0] not in "{[":
        name = Path(input_path).name
        _skip(f"  跳过: {name}（非明文 JSON，可能是 marketplace 加密/缓存）")
        return SKIP

    try:
        # MCBE 包常含 // 或 /* */ 注释（JSONC）；严格 json.loads 会失败
        data = loads_jsonc(content)
    except json.JSONDecodeError as e:
        name = Path(input_path).name
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

    # 内容无变化：不写盘、不建 backup
    if formatted == content:
        _p("内容已是规范格式，跳过")
        return True

    if output_path is None:
        backup_path = input_path + ".backup"
        _p(f"创建备份: {backup_path}")
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            _err(f"创建备份失败: {input_path} ({e})")
            return False

        output_path = input_path

    _p(f"正在写入文件: {output_path}")
    try:
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(formatted)
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
