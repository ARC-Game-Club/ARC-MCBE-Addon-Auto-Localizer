# -*- coding: utf-8 -*-
"""扫描本地模组包，并按 manifest UUID 依赖配对资源包 / 行为包。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .pack_rename_service import get_pack_roots, resolve_pack_display_name

_SUFFIX_RE = re.compile(r"(?:\s*[\[(_-]?\s*(BP|RP)\s*[\])]?)$", re.IGNORECASE)
_MC_FORMAT_CODES = re.compile(r"§.")


@dataclass
class PackInfo:
    path: Path
    kind: str  # "RP" | "BP"
    uuid: str
    dep_uuids: set[str]
    display_name: str


@dataclass
class ModEntry:
    """一个逻辑模组：可能同时有 RP / BP，也可能只有其一。"""
    name: str
    resource_pack: Path | None
    behavior_pack: Path | None

    @property
    def has_rp(self) -> bool:
        return self.resource_pack is not None

    @property
    def has_bp(self) -> bool:
        return self.behavior_pack is not None

    @property
    def pack_label(self) -> str:
        parts = []
        if self.has_rp:
            parts.append("RP")
        if self.has_bp:
            parts.append("BP")
        return "+".join(parts) if parts else "?"

    def pack_paths(self) -> list[Path]:
        out = []
        if self.resource_pack is not None:
            out.append(self.resource_pack)
        if self.behavior_pack is not None:
            out.append(self.behavior_pack)
        return out


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def _dep_uuids(data: dict) -> set[str]:
    deps = data.get("dependencies") or []
    if isinstance(deps, dict):
        deps = [deps]
    if not isinstance(deps, list):
        return set()
    out = set()
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        uid = dep.get("uuid")
        if isinstance(uid, str) and uid.strip():
            out.add(uid.strip().lower())
    return out


def _base_name(name: str) -> str:
    return _SUFFIX_RE.sub("", name).strip().casefold()


def scan_packs(base_dir: Path | None = None) -> list[PackInfo]:
    """扫描四个标准包目录，返回所有可读 manifest 的包。"""
    packs: list[PackInfo] = []
    for root, kind in get_pack_roots(base_dir):
        for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if not child.is_dir():
                continue
            mf = child / "manifest.json"
            if not mf.is_file():
                continue
            data = _read_json(mf)
            if not isinstance(data, dict):
                continue
            header = data.get("header") or {}
            uid = header.get("uuid")
            if not isinstance(uid, str) or not uid.strip():
                continue
            display, _err = resolve_pack_display_name(child)
            packs.append(
                PackInfo(
                    path=child,
                    kind=kind,
                    uuid=uid.strip().lower(),
                    dep_uuids=_dep_uuids(data),
                    display_name=display or child.name,
                )
            )
    return packs


def _pair_by_uuid(packs: list[PackInfo]) -> list[tuple[PackInfo | None, PackInfo | None]]:
    """按双向 UUID 依赖配对 (rp, bp)。未配对的单独返回。"""
    by_uuid = {p.uuid: p for p in packs}
    used: set[str] = set()
    pairs: list[tuple[PackInfo | None, PackInfo | None]] = []

    rps = [p for p in packs if p.kind == "RP"]
    bps = [p for p in packs if p.kind == "BP"]

    for bp in bps:
        if bp.uuid in used:
            continue
        partner = None
        for dep in bp.dep_uuids:
            cand = by_uuid.get(dep)
            if cand and cand.kind == "RP" and cand.uuid not in used:
                partner = cand
                break
        if partner is None:
            for rp in rps:
                if rp.uuid in used:
                    continue
                if bp.uuid in rp.dep_uuids:
                    partner = rp
                    break
        if partner is not None:
            used.add(bp.uuid)
            used.add(partner.uuid)
            pairs.append((partner, bp))

    for rp in rps:
        if rp.uuid in used:
            continue
        partner = None
        for dep in rp.dep_uuids:
            cand = by_uuid.get(dep)
            if cand and cand.kind == "BP" and cand.uuid not in used:
                partner = cand
                break
        if partner is not None:
            used.add(rp.uuid)
            used.add(partner.uuid)
            pairs.append((rp, partner))
        else:
            used.add(rp.uuid)
            pairs.append((rp, None))

    for bp in bps:
        if bp.uuid in used:
            continue
        used.add(bp.uuid)
        pairs.append((None, bp))

    return pairs


def _merge_name_pairs(
    pairs: list[tuple[PackInfo | None, PackInfo | None]],
) -> list[tuple[PackInfo | None, PackInfo | None]]:
    """对仍未配对的包，按去掉 BP/RP 后缀后的展示名再尝试合并。"""
    solo_rp = [rp for rp, bp in pairs if rp and not bp]
    solo_bp = [bp for rp, bp in pairs if bp and not rp]
    kept = [(rp, bp) for rp, bp in pairs if rp and bp]
    used_rp: set[str] = set()
    used_bp: set[str] = set()

    bp_by_base: dict[str, list[PackInfo]] = {}
    for bp in solo_bp:
        bp_by_base.setdefault(_base_name(bp.display_name), []).append(bp)

    for rp in solo_rp:
        key = _base_name(rp.display_name)
        cands = [b for b in bp_by_base.get(key, []) if b.uuid not in used_bp]
        if cands:
            bp = cands[0]
            used_rp.add(rp.uuid)
            used_bp.add(bp.uuid)
            kept.append((rp, bp))
        else:
            kept.append((rp, None))
            used_rp.add(rp.uuid)

    for bp in solo_bp:
        if bp.uuid not in used_bp:
            kept.append((None, bp))

    return kept


def list_mods(base_dir: Path | None = None) -> list[ModEntry]:
    """返回逻辑模组列表（已按依赖 / 同名配对）。"""
    packs = scan_packs(base_dir)
    pairs = _merge_name_pairs(_pair_by_uuid(packs))
    mods: list[ModEntry] = []
    for rp, bp in pairs:
        if rp and bp:
            name = rp.display_name or bp.display_name
            name = _SUFFIX_RE.sub("", name).strip() or name
        elif rp:
            name = rp.display_name
        else:
            name = bp.display_name  # type: ignore[union-attr]
        name = _MC_FORMAT_CODES.sub("", name).strip() or name
        mods.append(
            ModEntry(
                name=name,
                resource_pack=rp.path if rp else None,
                behavior_pack=bp.path if bp else None,
            )
        )
    mods.sort(key=lambda m: m.name.casefold())
    return mods
