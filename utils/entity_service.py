# -*- coding: utf-8 -*-
"""实体相关工具：怪物血量扫描、monster 标签添加。

底层实体判断逻辑复用 ui.entity_monster_family_gui。
"""
import json
from pathlib import Path

from ui.entity_monster_family_gui import (
    find_entity_files,
    entity_needs_monster_family,
    add_monster_to_entity_file,
    get_entity_health_for_reward,
    entity_has_monster_family_anywhere,
)


def list_pack_dirs(world_dir) -> list:
    """从世界目录或行为包目录解析出行为包列表。"""
    d = Path(world_dir)
    if not d.is_dir():
        return []
    if (d / "behavior_packs").is_dir():
        return [p for p in (d / "behavior_packs").iterdir() if p.is_dir()]
    return [d]


def entity_name_in_packs(packs, identifier) -> str:
    """从行为包 texts/*.lang 中查找实体的显示名。"""
    key = f"entity.{identifier}.name"
    for pack in packs:
        texts = pack / "texts"
        if not texts.is_dir():
            continue
        for lang in texts.glob("*.lang"):
            try:
                for line in lang.read_text(encoding="utf-8").splitlines():
                    if line.startswith(key + "="):
                        return line.split("=", 1)[1].strip()
            except OSError:
                continue
    return ""


def scan_monster_health(packs, log):
    """扫描怪物实体，返回 [(identifier, 血量字符串, 显示名)]。"""
    entries = []
    for pack in packs:
        for fp in sorted(find_entity_files(pack)):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            ent = data.get("minecraft:entity") or {}
            desc = ent.get("description") or {}
            identifier = (desc.get("identifier") or "").strip()
            if not identifier or ":" not in identifier:
                continue
            if not entity_has_monster_family_anywhere(data):
                continue
            hp = get_entity_health_for_reward(data)
            hp_str = str(hp) if hp is not None else "?"
            name = entity_name_in_packs(packs, identifier)
            entries.append((identifier, hp_str, name))
    return entries


def add_monster_tags(packs, log) -> int:
    """为攻击玩家的实体添加 monster 标签，返回添加数量。"""
    total = 0
    for pack in packs:
        for fp in sorted(find_entity_files(pack)):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if entity_has_monster_family_anywhere(data):
                continue
            if entity_needs_monster_family(fp, data):
                try:
                    add_monster_to_entity_file(fp)
                    log(f"  已添加 monster: {fp.name}")
                    total += 1
                except Exception as e:
                    log(f"  添加失败 {fp.name}: {e}")
    return total
