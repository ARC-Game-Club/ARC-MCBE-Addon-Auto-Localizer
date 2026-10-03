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
from .lang_files import ensure_texts_dir, read_lang_map, upsert_lang_entries
from .languages import DEFAULT_CODE, label_of
from .llm_service import translate_text
from .text_utils import needs_translation

# 已是语言键形态：item.foo:bar.name / entity.ns:id.name / item.spawn_egg.entity.ns:id.name
_LANG_KEY_RE = re.compile(r"^[A-Za-z][\w]*(\.[\w:]+)+$")

_ENTITY_COMPONENTS = ("minecraft:entity", "minecraft:client_entity")
_IDENT_COMPONENTS = (
    "minecraft:entity",
    "minecraft:client_entity",
    "minecraft:item",
    "minecraft:block",
)

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


def _rel_norm(rel: str | Path | None) -> str:
    return str(rel or "").replace("\\", "/").strip("/")


def _is_under(rel: str | Path | None, folder: str) -> bool:
    """相对路径是否位于 folder/ 下（blocks、items、entities 等）。"""
    r = _rel_norm(rel).casefold()
    f = folder.casefold().strip("/")
    if not r or not f:
        return False
    return r == f or r.startswith(f + "/")


def _identifier_of(data) -> str | None:
    """
    只取本定义 description.identifier（实际 namespace:id）。
    不递归进 components，避免跨 namespace 引用串前缀。
    """
    if not isinstance(data, dict):
        return None
    for comp_key in _IDENT_COMPONENTS:
        comp = data.get(comp_key)
        if isinstance(comp, dict):
            desc = comp.get("description")
            if isinstance(desc, dict):
                ident = (desc.get("identifier") or "").strip()
                if ident and ":" in ident:
                    return ident
    desc = data.get("description")
    if isinstance(desc, dict):
        ident = (desc.get("identifier") or "").strip()
        if ident and ":" in ident:
            return ident
    return None


# 兼容旧名
def _find_identifier(data) -> str | None:
    return _identifier_of(data)


def derive_lang_key(data, rel_path: str | Path | None = None) -> str | None:
    """
    按优先级推导语言键（namespace 一律来自 JSON identifier，不猜默认）：

      1. 实体 / client_entity 且 description 含 spawn_egg
         → item.spawn_egg.entity.<ns>:<id>.name
      2. 实体 / client_entity（无 spawn_egg）
         → entity.<ns>:<id>.name
      3. minecraft:block，或路径在 blocks/ 下
         → tile.<ns>:<id>.name
      4. minecraft:item，或路径在 items/ 下
         → item.<ns>:<id>.name
    """
    if not isinstance(data, dict):
        return None
    rel = _rel_norm(rel_path)

    for comp_key in _ENTITY_COMPONENTS:
        comp = data.get(comp_key)
        if not isinstance(comp, dict):
            continue
        desc = comp.get("description")
        if not isinstance(desc, dict):
            continue
        ident = (desc.get("identifier") or "").strip()
        if not ident or ":" not in ident:
            continue
        if "spawn_egg" in desc:
            return f"item.spawn_egg.entity.{ident}.name"
        return f"entity.{ident}.name"

    if "minecraft:block" in data or _is_under(rel, "blocks"):
        ident = _identifier_of(data)
        if ident:
            return f"tile.{ident}.name"

    if "minecraft:item" in data or _is_under(rel, "items"):
        ident = _identifier_of(data)
        if ident:
            return f"item.{ident}.name"

    return None


def collect_pack_namespaces(pack_dir: Path, log=None) -> set[str]:
    """扫描包内 entity/item/block JSON 的 identifier，建立实际 namespace 集合。"""
    pack_dir = Path(pack_dir)
    namespaces: set[str] = set()
    for fp in find_json_files(pack_dir):
        try:
            rel = fp.relative_to(pack_dir)
        except ValueError:
            rel = fp
        parts = {p.casefold() for p in Path(rel).parts}
        if "texts" in parts or "_backup" in parts:
            continue
        try:
            data = loads_jsonc(fp.read_text(encoding="utf-8-sig"))
        except Exception as e:
            if log is not None:
                log(f"  跳过（解析失败）: {rel}: {e}")
            continue
        ident = _identifier_of(data)
        if ident and ":" in ident:
            namespaces.add(ident.split(":", 1)[0].strip())
    return {ns for ns in namespaces if ns}


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


def _collect_display_name_entries(
    pack_dir: Path, log
) -> tuple[list[tuple[Path, object, str, str]], set[str]]:
    """
    Pass 1：递归收集全部 display_name；单文件失败只记日志，不中断整包。
    返回 ([(abs_path, data, value, rel), ...], namespaces)。
    """
    pack_dir = Path(pack_dir)
    entries: list[tuple[Path, object, str, str]] = []
    namespaces: set[str] = set()

    for fp in find_json_files(pack_dir):
        try:
            rel_path = fp.relative_to(pack_dir)
        except ValueError:
            continue
        parts = {p.casefold() for p in rel_path.parts}
        if "texts" in parts or "_backup" in parts:
            continue
        rel = str(rel_path)
        try:
            raw = fp.read_text(encoding="utf-8-sig")
            data = loads_jsonc(raw)
        except Exception as e:
            log(f"  跳过（解析失败）: {rel}: {e}")
            continue

        ident = _identifier_of(data)
        if ident and ":" in ident:
            namespaces.add(ident.split(":", 1)[0].strip())

        try:
            value = find_display_name_recursive(data)
        except Exception as e:
            log(f"  跳过（读取 display_name 失败）: {rel}: {e}")
            continue
        if value is None:
            continue
        entries.append((fp, data, value, rel))

    return entries, {ns for ns in namespaces if ns}


def _pack_role(label: str, pack: Path) -> str | None:
    """返回 'rp' / 'bp'。优先用调用方标签，否则看目录名。"""
    if label == "资源包":
        return "rp"
    if label == "行为包":
        return "bp"
    parts = {p.casefold() for p in Path(pack).parts}
    if parts & {"resource_packs", "development_resource_packs"}:
        return "rp"
    if parts & {"behavior_packs", "development_behavior_packs"}:
        return "bp"
    return None


def _mirror_display_name_langs(
    rp_dir: Path,
    target_code: str,
    en_map: dict[str, str],
    target_map: dict[str, str],
    log,
) -> None:
    """把行为包本次整理出的语言键追加到资源包。已有键不覆盖。"""
    log(f"  同步语言键到资源包: {Path(rp_dir).name}")
    texts = ensure_texts_dir(rp_dir, target_code, log)
    if texts is None:
        log("  无法准备资源包 texts/，语言键未同步")
        return
    upsert_lang_entries(texts / "en_US.lang", en_map, log)
    upsert_lang_entries(texts / f"{target_code}.lang", target_map, log)


def standardize_display_names_in_pack(
    pack_dir: Path,
    target_code: str,
    log,
    llm_cfg=None,
    mirror_to: Path | None = None,
) -> tuple[int, int, int]:
    """
    标准化包内 display_name：
      - 可推导 key → JSON 写 key，原文补入 en_US.lang 与目标语言 .lang
      - 已是 lang key 但与推导结果不一致 → 修正为正确 key
      - 已是正确 lang key → 跳过改写，仍确保语言文件有条目
      - 无法推导 → 回退 LLM 直译写回 value
      - mirror_to 给定时，把本次语言键再追加到该包（资源包）

    返回 (扫描到的 display_name 数, 标准化数, 回退直译数)。
    """
    pack_dir = Path(pack_dir)
    target_code = (target_code or DEFAULT_CODE).strip() or DEFAULT_CODE
    lang_label = label_of(target_code)

    texts = ensure_texts_dir(pack_dir, target_code, log)
    if texts is None:
        log("无法准备 texts/，跳过 display_name 标准化")
        return 0, 0, 0

    # Pass 1：收集（含子目录）；失败单文件跳过
    entries, namespaces = _collect_display_name_entries(pack_dir, log)
    if namespaces:
        log(f"  检测到 namespace: {', '.join(sorted(namespaces))}")
    else:
        log("  未从 identifier 检测到 namespace（仅处理已有 display_name）")

    existing_en = read_lang_map(texts / "en_US.lang")
    en_map: dict[str, str] = {}
    target_map: dict[str, str] = {}
    fallback: list[tuple[Path, str]] = []
    found = len(entries)
    standardized = 0

    # Pass 2：基于完整列表逐一推导 / 写回
    for fp, data, value, rel in entries:
        correct = derive_lang_key(data, rel)

        if _looks_like_lang_key(value):
            key = value.strip()
            if correct and correct != key:
                english = existing_en.get(key) or existing_en.get(correct) or key
                en_map[correct] = english
                target_map[correct] = english
                if _set_display_name_value(data, correct):
                    try:
                        _write_json(fp, data)
                        standardized += 1
                        log(f"  修正语言键: {rel}: {key} → {correct}")
                    except OSError as e:
                        log(f"  写入失败 {rel}: {e}")
                else:
                    log(f"  语言键需修正但未能改写 JSON: {rel}: {key} → {correct}")
                continue

            en_map.setdefault(key, existing_en.get(key, key))
            target_map.setdefault(key, existing_en.get(key, key))
            log(f"  已是语言键，跳过改写: {rel} → {key}")
            continue

        if correct is None:
            log(f"  无法推导标准 key，加入回退清单: {rel}")
            fallback.append((fp, value))
            continue

        en_map[correct] = value
        target_map[correct] = value
        if _set_display_name_value(data, correct):
            try:
                _write_json(fp, data)
                standardized += 1
                log(f"  标准化: {rel} → {correct}")
            except OSError as e:
                log(f"  写入失败 {rel}: {e}")
        else:
            log(f"  未改动 JSON（值已是 key?）: {rel}")
            standardized += 1

    if en_map:
        upsert_lang_entries(texts / "en_US.lang", en_map, log)
        upsert_lang_entries(texts / f"{target_code}.lang", target_map, log)
        if mirror_to is not None and Path(mirror_to).resolve() != pack_dir.resolve():
            _mirror_display_name_langs(
                mirror_to, target_code, en_map, target_map, log
            )

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
    """对多个包执行标准化。行为包整理出的语言键会同步写入资源包。

    返回合计 (found, standardized, fallback)。
    """
    rp_dir = next(
        (pack for label, pack in packs if _pack_role(label, pack) == "rp"),
        None,
    )
    total_f = total_s = total_b = 0
    for label, pack in packs:
        log(f"—— {label}: {pack.name} ——")
        mirror = rp_dir if _pack_role(label, pack) == "bp" else None
        f, s, b = standardize_display_names_in_pack(
            pack, target_code, log, llm_cfg, mirror_to=mirror
        )
        total_f += f
        total_s += s
        total_b += b
    return total_f, total_s, total_b
