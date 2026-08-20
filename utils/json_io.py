# -*- coding: utf-8 -*-
"""读取 Minecraft 包内常见的 JSONC（允许 // 与 /* */ 注释）。"""
from __future__ import annotations

import json
from pathlib import Path


def strip_json_comments(text: str) -> str:
    """去掉字符串外的 // 行注释与 /* */ 块注释。"""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i += 2
                while i < n and text[i] not in "\r\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i = min(i + 2, n)
                continue
        out.append(c)
        i += 1
    return "".join(out)


def loads_jsonc(text: str):
    """解析可能含注释的 JSON 文本。"""
    return json.loads(strip_json_comments(text))


def read_json_file(path: Path):
    """读取 JSON/JSONC 文件；失败返回 None。"""
    try:
        return loads_jsonc(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
