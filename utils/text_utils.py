# -*- coding: utf-8 -*-
"""通用文本辅助函数。"""
import re

from .languages import get


def _count_script_chars(text: str, script: str) -> int:
    """统计文本中属于目标文字系统的字符数。"""
    if script == "han":
        return sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if script == "kana":
        return sum(
            1
            for c in text
            if ("\u3040" <= c <= "\u30ff")  # 平假名 / 片假名
            or ("\u4e00" <= c <= "\u9fff")  # 日语也常用汉字
            or ("\uff66" <= c <= "\uff9d")  # 半角片假名
        )
    if script == "hangul":
        return sum(
            1
            for c in text
            if ("\uac00" <= c <= "\ud7af")  # 韩文音节
            or ("\u1100" <= c <= "\u11ff")  # 韩文字母
        )
    if script == "cyrillic":
        return sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    if script == "greek":
        return sum(1 for c in text if "\u0370" <= c <= "\u03ff")
    return 0


def needs_translation(text: str, target_code: str | None = None) -> bool:
    """判断文本是否仍需要翻译到目标语言。"""
    if not text or not text.strip():
        return False
    alpha = sum(1 for c in text if c.isalpha())
    if alpha == 0:
        return False
    lang = get(target_code)
    if lang.script == "latin":
        # 拉丁语系之间无法靠字符集区分，交由调用方用 en_US 对照等信号判断
        return True
    script_chars = _count_script_chars(text, lang.script)
    return script_chars / max(alpha, 1) < 0.2


def is_english_text(text: str) -> bool:
    """兼容旧调用：等价于目标简体中文时的 needs_translation。"""
    return needs_translation(text, "zh_CN")


def extract_urls(text: str):
    """提取文本中出现的 URL 列表。"""
    return re.findall(r"https?://[^\s\)\]\"']+", text or "")
