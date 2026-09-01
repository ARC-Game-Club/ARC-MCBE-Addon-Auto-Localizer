# -*- coding: utf-8 -*-
"""display_name 标准化：写成语言文件 key，无法推导时回退直译。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ui.display_name_tool_gui import (
    find_display_name_recursive,
    find_json_files,
    update_display_name_recursive,
)

from .json_io import loads_jsonc
from .lang_files import ensure_texts_dir, upsert_lang_entries
from .languages import DEFAULT_CODE, label_of
from .llm_service import translate_text
from .text_utils import needs_translation

# 已是语言键形态：item.foo:bar.name / entity.ns:id.name
_LANG_KEY_RE = re.compile(r"^[A-Za-z][\w]*(\.[\w:]+)+$")

_COMPONENT_KEY_PREFIX = {
    "minecraft:entity": "entity",
    "minecraft:item": "item",
    "minecraft:block": "tile",
}

FALLBACK_TRANSLATE_PROMPT = """你是一名 Minecraft 基岩版模组本地化专家。
下面是无法标准化为语言文件 key 的 display_name 映射，每行格式为：相对路径=JSON字符串字面量。
请把每个等号右边的显示名翻译成{lang_label}，输出保持原格式（相对路径=JSON字符串），
只改值不改键。注意值需要用 JSON 字符串语法（引号包裹，转义 \\n、§ 颜色码等保留）。
直接输出全部翻译结果，不要任何解释。

内容：
{content}
"""


def _looks_like_lang_key(value: str) -> bool:
    return bool(value and _LANG_KEY_RE.fullmatch(value.strip()))


def _find_identifier(data) -> str | None:
    """从 JSON 根/递归结构中找 description.identifier。"""
    if not isinstance(data, dict):
        return None
    # 常见：minecraft:entity / item / block 下 description.identifier
    for comp_key in _COMPONENT_KEY_PREFIX:
        comp = data.get(comp_key)
        if isinstance(comp, dict):
            desc = comp.get("description")
            if isinstance(desc, dict):
                ident = (desc.get("identifier") or "").strip()
                if ident and ":" in ident:
                    return ident
    # 兜底：任意 description.identifier
    desc = data.get("description")
    if isinstance(desc, dict):
        ident = (desc.get("identifier") or "").strip()
        if ident and ":" in ident:
            return ident
    for v in data.values():
        if isinstance(v, dict):
            found = _find_identifier(v)
            if found:
                return found
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    found = _find_identifier(item)
                    if found:
                        return found
    return None


def _detect_component(data) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in _COMPONENT_KEY_PREFIX:
        if key in data:
            return key
    return None


def derive_lang_key(data) -> str | None:
    """根据 JSON 根组件 + identifier 生成标准语言键；失败返回 None。"""
    component = _detect_component(data)
    if component is None:
        return None
    prefix = _COMPONENT_KEY_PREFIX[component]
    ident = _find_identifier(data)
    if not ident:
        return None
    return f"{prefix}.{ident}.name"


def _set_display_name_value(data, new_value: str) -> bool:
    """把 minecraft:display_name 写为 new_value（字符串或 value 字段）。"""
    return update_display_name_recursive(data, new_value)


def _write_json(fp: Path, data) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    fp.write_text(text, encoding="utf-8")


def _parse_fallback_mapping(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in (text or "").splitlines():
        if not line.strip() or "=" not in line:
            continue
        left, right = line.split("=", 1)
        try:
            mapping[left] = json.loads(right)
        except json.JSONDecodeError:
            mapping[left] = right
    return mapping


def standardize_display_names_in_pack(
    pack_dir: Path,
    target_code: str,
    log,
    llm_cfg=None,
) -> tuple[int, int, int]:
    """
    标准化包内 display_name：
      - 可推导 key → JSON 写 key，原文补入 en_US.lang 与目标语言 .lang
      - 已是 lang key → 跳过改写，仍确保语言文件有条目（值取现有英文或 key）
      - 无法推导 → 回退 LLM 直译写回 value

    返回 (扫描到的 display_name 数, 标准化数, 回退直译数)。
    """
    pack_dir = Path(pack_dir)
    target_code = (target_code or DEFAULT_CODE).strip() or DEFAULT_CODE
    lang_label = label_of(target_code)

    texts = ensure_texts_dir(pack_dir, target_code, log)
    if texts is None:
        log("无法准备 texts/，跳过 display_name 标准化")
        return 0, 0, 0

    en_map: dict[str, str] = {}
    target_map: dict[str, str] = {}
    fallback: list[tuple[Path, str]] = []  # (abs path, original display value)
    found = 0
    standardized = 0

    for fp in find_json_files(pack_dir):
        # 跳过 texts / 备份
        parts = {p.casefold() for p in fp.relative_to(pack_dir).parts}
        if "texts" in parts or "_backup" in parts:
            continue
        try:
            data = loads_jsonc(fp.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        value = find_display_name_recursive(data)
        if value is None:
            continue
        found += 1
        rel = str(fp.relative_to(pack_dir))

        if _looks_like_lang_key(value):
            key = value.strip()
            # 已标准化：若语言文件尚无此 key，用 key 本身作占位（避免空）
            en_map.setdefault(key, key)
            target_map.setdefault(key, key)
            log(f"  已是语言键，跳过改写: {rel} → {key}")
            continue

        key = derive_lang_key(data)
        if key is None:
            log(f"  无法推导标准 key，加入回退清单: {rel}")
            fallback.append((fp, value))
            continue

        # 原文写入语言文件；JSON 改为 key
        en_map[key] = value
        target_map[key] = value
        if _set_display_name_value(data, key):
            try:
                _write_json(fp, data)
                standardized += 1
                log(f"  标准化: {rel} → {key}")
            except OSError as e:
                log(f"  写入失败 {rel}: {e}")
        else:
            log(f"  未改动 JSON（值已是 key?）: {rel}")
            standardized += 1

    if en_map:
        upsert_lang_entries(texts / "en_US.lang", en_map, log)
        upsert_lang_entries(texts / f"{target_code}.lang", target_map, log)

    fallback_done = 0
    if fallback:
        if not llm_cfg or not (llm_cfg.get("api_key") or "").strip():
            log(f"  有 {len(fallback)} 条无法标准化，但未配置文本 LLM，跳过直译")
        else:
            log(f"  回退直译 {len(fallback)} 条（→ {lang_label}）…")
            lines = [
                f"{fp.relative_to(pack_dir)}={json.dumps(val, ensure_ascii=False)}"
                for fp, val in fallback
            ]
            content = "\n".join(lines)
            try:
                out = translate_text(
                    llm_cfg,
                    FALLBACK_TRANSLATE_PROMPT.format(
                        lang_label=lang_label, content=content
                    ),
                    log,
                )
            except Exception as e:
                log(f"  回退翻译失败: {e}")
                out = ""
            translated = _parse_fallback_mapping(out)
            for fp, old_val in fallback:
                rel = str(fp.relative_to(pack_dir))
                new_val = translated.get(rel)
                if not new_val or new_val == old_val:
                    # 若目标已是目标语言且过滤器认为无需译，也算跳过
                    if not needs_translation(old_val, target_code):
                        continue
                    continue
                try:
                    data = loads_jsonc(fp.read_text(encoding="utf-8-sig"))
                except Exception as e:
                    log(f"  回退写回跳过 {rel}: {e}")
                    continue
                if _set_display_name_value(data, new_val):
                    try:
                        _write_json(fp, data)
                        fallback_done += 1
                        log(f"  回退直译写回: {rel}")
                    except OSError as e:
                        log(f"  回退写回失败 {rel}: {e}")

    return found, standardized, fallback_done


def standardize_display_names_for_mod(
    packs: list[tuple[str, Path]],
    target_code: str,
    log,
    llm_cfg=None,
) -> tuple[int, int, int]:
    """对多个包执行标准化，返回合计 (found, standardized, fallback)。"""
    total_f = total_s = total_b = 0
    for label, pack in packs:
        log(f"—— {label}: {pack.name} ——")
        f, s, b = standardize_display_names_in_pack(pack, target_code, log, llm_cfg)
        total_f += f
        total_s += s
        total_b += b
    return total_f, total_s, total_b
