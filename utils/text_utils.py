# -*- coding: utf-8 -*-
"""通用文本辅助函数。"""
import re


def is_english_text(text: str) -> bool:
    """粗略判断文本是否主要为英文（需要翻译）。"""
    if not text or not text.strip():
        return False
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    alpha = sum(1 for c in text if c.isalpha())
    if alpha == 0:
        return False
    return chinese / max(alpha, 1) < 0.2


def extract_urls(text: str):
    """提取文本中出现的 URL 列表。"""
    return re.findall(r"https?://[^\s\)\]\"']+", text or "")
