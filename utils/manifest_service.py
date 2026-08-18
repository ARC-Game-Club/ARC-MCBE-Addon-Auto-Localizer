# -*- coding: utf-8 -*-
"""模组 manifest.json 处理（灵动视效 PBR、成就兼容、字面量包名翻译等）。"""
import json
import shutil
from pathlib import Path

from .credit_service import with_credit
from .languages import DEFAULT_CODE, strip_credit_suffix
from .llm_service import translate_lang_batch
from .text_utils import needs_translation


def read_manifest(pack_path: Path):
    """读取包目录下 manifest.json，返回 (data, error)。"""
    manifest = Path(pack_path) / "manifest.json"
    if not manifest.exists():
        return None, "manifest.json 不存在"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return data, None
    except (json.JSONDecodeError, OSError) as e:
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


def localize_manifest_header(
    pack_path: Path,
    llm_cfg,
    log,
    code: str | None = None,
    lang_label: str = "简体中文",
    credit: str | None = None,
) -> bool:
    """
    翻译 manifest.header 里直接写死的名称 / 简介（不是 pack.name 那种语言键）。
    名称翻译后若传入 credit，会一并加上署名后缀。
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
    pending: list[tuple[str, str]] = []
    originals: dict[str, str] = {}
    for field, lang_key in _HEADER_LANG_KEYS.items():
        raw = header.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        if raw.strip() == lang_key:
            continue
        base = strip_credit_suffix(raw) if field == "name" else raw
        if not needs_translation(base, code):
            continue
        pending.append((f"header.{field}", base))
        originals[field] = raw

    if not pending:
        return False

    log(f"  翻译 manifest 字面量: {', '.join(originals)}")
    result = translate_lang_batch(pending, llm_cfg, log, lang_label=lang_label)
    changed = False
    for field, old in originals.items():
        translated = (result.get(f"header.{field}") or "").strip()
        if not translated or translated == strip_credit_suffix(old):
            continue
        if field == "name" and credit:
            translated = with_credit(translated, credit, code)
        header[field] = translated
        log(f"  manifest.{field}: {old} → {translated}")
        changed = True
    if not changed:
        log("  manifest 字面量翻译无变化")
        return False
    data["header"] = header
    return _write_manifest(manifest, data, log, "  已写回 manifest.json")
