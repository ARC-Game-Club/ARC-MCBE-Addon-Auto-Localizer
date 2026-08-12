# -*- coding: utf-8 -*-
"""MCBE 官方语言码定义与署名后缀模板。"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    label: str
    credit_suffix: str  # 含 {credit}
    script: str  # "han" | "kana" | "hangul" | "latin" | "cyrillic" | "greek"


# MCBE 官方支持的 29 个语言码（见 Microsoft Learn Comprehensive Pack Contents）
LANGUAGES: list[Language] = [
    Language("zh_CN", "简体中文", "（{credit}汉化）", "han"),
    Language("zh_TW", "繁體中文", "（{credit}漢化）", "han"),
    Language("en_US", "英语（美国）", "({credit} Localization)", "latin"),
    Language("en_GB", "英语（英国）", "({credit} Localization)", "latin"),
    Language("ja_JP", "日语", "（{credit}翻訳）", "kana"),
    Language("ko_KR", "韩语", "({credit} 번역)", "hangul"),
    Language("de_DE", "德语", "({credit} Localization)", "latin"),
    Language("fr_FR", "法语", "({credit} Localization)", "latin"),
    Language("fr_CA", "法语（加拿大）", "({credit} Localization)", "latin"),
    Language("es_ES", "西班牙语", "({credit} Localization)", "latin"),
    Language("es_MX", "西班牙语（墨西哥）", "({credit} Localization)", "latin"),
    Language("pt_BR", "葡萄牙语（巴西）", "({credit} Localization)", "latin"),
    Language("pt_PT", "葡萄牙语", "({credit} Localization)", "latin"),
    Language("it_IT", "意大利语", "({credit} Localization)", "latin"),
    Language("nl_NL", "荷兰语", "({credit} Localization)", "latin"),
    Language("ru_RU", "俄语", "({credit} Localization)", "cyrillic"),
    Language("uk_UA", "乌克兰语", "({credit} Localization)", "cyrillic"),
    Language("pl_PL", "波兰语", "({credit} Localization)", "latin"),
    Language("cs_CZ", "捷克语", "({credit} Localization)", "latin"),
    Language("sk_SK", "斯洛伐克语", "({credit} Localization)", "latin"),
    Language("hu_HU", "匈牙利语", "({credit} Localization)", "latin"),
    Language("tr_TR", "土耳其语", "({credit} Localization)", "latin"),
    Language("sv_SE", "瑞典语", "({credit} Localization)", "latin"),
    Language("da_DK", "丹麦语", "({credit} Localization)", "latin"),
    Language("nb_NO", "挪威语", "({credit} Localization)", "latin"),
    Language("fi_FI", "芬兰语", "({credit} Localization)", "latin"),
    Language("el_GR", "希腊语", "({credit} Localization)", "greek"),
    Language("bg_BG", "保加利亚语", "({credit} Localization)", "cyrillic"),
    Language("id_ID", "印尼语", "({credit} Localization)", "latin"),
]

DEFAULT_CODE = "zh_CN"

_BY_CODE: dict[str, Language] = {lang.code: lang for lang in LANGUAGES}


def get(code: str | None) -> Language:
    """按语言码取 Language；未知码回退默认简体中文。"""
    code = (code or "").strip()
    return _BY_CODE.get(code, _BY_CODE[DEFAULT_CODE])


def label_of(code: str | None) -> str:
    return get(code).label


def credit_suffix(code: str | None, credit: str) -> str:
    credit = (credit or "").strip() or "DEVILENMO"
    return get(code).credit_suffix.format(credit=credit)


def _build_credit_strip_re() -> re.Pattern[str]:
    """用全部署名模板拼出能剥掉任意语言旧后缀的正则。"""
    parts: list[str] = []
    seen: set[str] = set()
    for lang in LANGUAGES:
        tmpl = lang.credit_suffix
        # 全角括号形式：（…）
        if tmpl.startswith("（") and tmpl.endswith("）"):
            mid = tmpl[1:-1].replace("{credit}", r"[^）]*")
            pat = f"（{mid}）"
        # 半角括号形式：(...)
        elif tmpl.startswith("(") and tmpl.endswith(")"):
            mid = tmpl[1:-1].replace("{credit}", r"[^)]*")
            pat = f"\\({mid}\\)"
        else:
            continue
        if pat not in seen:
            seen.add(pat)
            parts.append(pat)
    # 兼容旧版固定中文署名
    for extra in (r"（[^）]*汉化）", r"（[^）]*漢化）"):
        if extra not in seen:
            parts.append(extra)
    return re.compile(r"(?:\s*(?:" + "|".join(parts) + r"))\s*$")


_CREDIT_STRIP_RE = _build_credit_strip_re()


def strip_credit_suffix(name: str) -> str:
    """去掉任意语言的本地化署名后缀。"""
    return _CREDIT_STRIP_RE.sub("", (name or "").rstrip()).rstrip()
