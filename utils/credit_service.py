# -*- coding: utf-8 -*-
"""本地化者署名：在 pack.name / manifest 包名后追加署名后缀。"""
from __future__ import annotations

import json
from pathlib import Path

from .json_io import loads_jsonc
from .lang_files import read_lang_map, upsert_lang_entries
from .languages import DEFAULT_CODE, credit_suffix, strip_credit_suffix
from .license_service import write_localization_license


def format_credit_suffix(credit: str, code: str | None = None) -> str:
    credit = (credit or "").strip()
    if not credit:
        raise ValueError("署名为空")
    return credit_suffix(code or DEFAULT_CODE, credit)


def with_credit(name: str, credit: str, code: str | None = None) -> str:
    """在名称后追加或替换署名后缀。"""
    suffix = format_credit_suffix(credit, code)
    base = strip_credit_suffix(name or "")
    if not base:
        base = name or "pack"
    return base + suffix


def _update_lang_pack_name(lang_path: Path, credit: str, code: str, log) -> bool:
    try:
        content = lang_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as e:
        log(f"无法读取: {lang_path} ({e})")
        return False
    if "pack.name=" not in content:
        return False
    out_lines = []
    found = False
    changed = False
    for line in content.splitlines():
        if line.startswith("pack.name="):
            old = line.split("=", 1)[1]
            new = with_credit(old, credit, code)
            out_lines.append(f"pack.name={new}")
            found = True
            if new != old:
                changed = True
        else:
            out_lines.append(line)
    if not found:
        return False
    if not changed:
        log(f"{lang_path.name}: pack.name 已含署名，跳过")
        return True
    new_text = "\n".join(out_lines)
    if content.endswith("\n"):
        new_text += "\n"
    lang_path.write_text(new_text, encoding="utf-8")
    log(f"已更新 {lang_path.name}: pack.name → {format_credit_suffix(credit, code)}")
    return True


def _update_manifest_name(pack_dir: Path, credit: str, code: str, log) -> bool:
    mf = pack_dir / "manifest.json"
    if not mf.is_file():
        return False
    try:
        data = loads_jsonc(mf.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError) as e:
        log(f"manifest 读取失败: {e}")
        return False
    header = data.get("header")
    if not isinstance(header, dict):
        return False
    name = header.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    if name.strip() == "pack.name":
        log("manifest.name 为 pack.name，改在语言文件中署名")
        return False
    new_name = with_credit(name, credit, code)
    if new_name == name:
        log(f"manifest: 已含署名，跳过 ({pack_dir.name})")
        return True
    header["name"] = new_name
    data["header"] = header
    mf.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    log(f"已更新 manifest.json name → {new_name}")
    return True


def apply_translator_credit(
    pack_dir: Path, credit: str, log, code: str | None = None
) -> bool:
    """
    对单个包应用署名：
    - 改目标语言 .lang 的 pack.name（若缺失则从 en_US 补全）
    - 若 manifest.header.name 不是 pack.name，则直接改 manifest
    """
    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    pack_dir = Path(pack_dir)
    if not pack_dir.is_dir():
        log(f"包不存在: {pack_dir}")
        return False
    ok = False
    texts = pack_dir / "texts"
    if texts.is_dir():
        target_lang = texts / f"{code}.lang"
        en_us = texts / "en_US.lang"
        if target_lang.is_file() and en_us.is_file():
            en_map = read_lang_map(en_us)
            target_map = read_lang_map(target_lang)
            missing = {
                k: en_map[k]
                for k in ("pack.name", "pack.description")
                if k in en_map and k not in target_map
            }
            if missing:
                upsert_lang_entries(target_lang, missing, log)
        if target_lang.is_file() and _update_lang_pack_name(target_lang, credit, code, log):
            ok = True
    if _update_manifest_name(pack_dir, credit, code, log):
        ok = True
    if write_localization_license(pack_dir, credit, log, code=code):
        ok = True
    if not ok:
        log(f"未能在 {pack_dir.name} 中找到可署名的包名")
    return ok


def apply_credit_to_mod(
    rp: Path | None,
    bp: Path | None,
    credit: str,
    log,
    code: str | None = None,
) -> int:
    """对模组下已有的包应用署名，返回成功包数。"""
    n = 0
    for label, path in (("资源包", rp), ("行为包", bp)):
        if path is None:
            continue
        log(f"—— {label}: {path.name} ——")
        if apply_translator_credit(path, credit, log, code=code):
            n += 1
    return n
