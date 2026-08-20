# -*- coding: utf-8 -*-
"""模组 manifest.json 处理（灵动视效 PBR、成就兼容、包名语言键等）。"""
import json
import shutil
from pathlib import Path

from .json_io import loads_jsonc
from .lang_files import ensure_texts_dir, upsert_lang_entries
from .languages import DEFAULT_CODE, strip_credit_suffix


def read_manifest(pack_path: Path):
    """读取包目录下 manifest.json，返回 (data, error)。"""
    manifest = Path(pack_path) / "manifest.json"
    if not manifest.exists():
        return None, "manifest.json 不存在"
    try:
        data = loads_jsonc(manifest.read_text(encoding="utf-8-sig"))
        return data, None
    except (json.JSONDecodeError, OSError, UnicodeError) as e:
        return None, f"读取失败: {e}"


def _write_manifest(manifest: Path, data: dict, log, ok_msg: str) -> bool:
    try:
        shutil.copy2(str(manifest), str(manifest) + ".backup")
        manifest.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        log(ok_msg)
        return True
    except OSError as e:
        log(f"写入失败: {e}")
        return False


def apply_pbr_capability(resource_pack_path: Path, log) -> bool:
    """为 manifest.json 添加 pbr capability。"""
    manifest = Path(resource_pack_path) / "manifest.json"
    data, err = read_manifest(resource_pack_path)
    if err:
        log(f"错误: {err}")
        return False
    caps = data.get("capabilities")
    if caps is None:
        caps = []
        data["capabilities"] = caps
    if not isinstance(caps, list):
        log("错误: capabilities 字段不是数组")
        return False
    if "pbr" in caps:
        log("pbr capability 已存在，无需修改")
        return True
    caps.append("pbr")
    return _write_manifest(
        manifest, data, log, "已添加 pbr capability，并备份原 manifest"
    )


def has_addon_product_type(data: dict | None) -> bool:
    """manifest 是否已声明 metadata.product_type == addon。"""
    if not isinstance(data, dict):
        return False
    md = data.get("metadata")
    return isinstance(md, dict) and md.get("product_type") == "addon"


def apply_addon_product_type(pack_path: Path, log) -> bool:
    """写入 metadata.product_type = addon（成就友好），保留其它 metadata 字段。"""
    pack_path = Path(pack_path)
    manifest = pack_path / "manifest.json"
    data, err = read_manifest(pack_path)
    if err:
        log(f"错误 [{pack_path.name}]: {err}")
        return False
    md = data.get("metadata")
    if md is None:
        md = {}
        data["metadata"] = md
    if not isinstance(md, dict):
        log(f"错误 [{pack_path.name}]: metadata 字段不是对象")
        return False
    if md.get("product_type") == "addon":
        log(f"[{pack_path.name}] product_type=addon 已存在，跳过")
        return True
    md["product_type"] = "addon"
    return _write_manifest(
        manifest,
        data,
        log,
        f"[{pack_path.name}] 已添加 metadata.product_type=addon，并备份原 manifest",
    )


def remove_addon_product_type(pack_path: Path, log) -> bool:
    """移除 metadata.product_type；若 metadata 变空则删除该字段。"""
    pack_path = Path(pack_path)
    manifest = pack_path / "manifest.json"
    data, err = read_manifest(pack_path)
    if err:
        log(f"错误 [{pack_path.name}]: {err}")
        return False
    md = data.get("metadata")
    if not isinstance(md, dict) or "product_type" not in md:
        log(f"[{pack_path.name}] 无 product_type，跳过")
        return True
    del md["product_type"]
    if not md:
        data.pop("metadata", None)
    return _write_manifest(
        manifest,
        data,
        log,
        f"[{pack_path.name}] 已移除 product_type，并备份原 manifest",
    )


_HEADER_LANG_KEYS = {
    "name": "pack.name",
    "description": "pack.description",
}


def normalize_manifest_header_keys(
    pack_path: Path, log, code: str | None = None
) -> bool:
    """
    若 header.name / description 是字面量，改成 pack.name / pack.description，
    并把原文写入语言文件。翻译与署名仍由后续语言文件步骤处理。
    """
    pack_path = Path(pack_path)
    manifest = pack_path / "manifest.json"
    data, err = read_manifest(pack_path)
    if err:
        log(f"  manifest: {err}")
        return False
    header = data.get("header")
    if not isinstance(header, dict):
        return False

    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    entries: dict[str, str] = {}
    for field, lang_key in _HEADER_LANG_KEYS.items():
        raw = header.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        if raw.strip() == lang_key:
            continue
        value = strip_credit_suffix(raw).strip() if field == "name" else raw.strip()
        if not value:
            continue
        entries[lang_key] = value
        header[field] = lang_key
        log(f"  manifest.{field}: {raw} → {lang_key}")

    if not entries:
        return False

    texts = ensure_texts_dir(pack_path, code, log)
    if texts is None:
        return False
    upsert_lang_entries(texts / "en_US.lang", entries, log)
    target_lang = texts / f"{code}.lang"
    if target_lang.is_file():
        upsert_lang_entries(target_lang, entries, log)
    data["header"] = header
    return _write_manifest(manifest, data, log, "  已将包名/简介改为语言键并写回 manifest.json")
