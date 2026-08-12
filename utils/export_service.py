# -*- coding: utf-8 -*-
"""导出本地化包为 .mcpack / .mcaddon（均为 ZIP 改后缀）。"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .credit_service import with_credit
from .languages import DEFAULT_CODE, strip_credit_suffix

_INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MC_FORMAT = re.compile(r"§.")
_SKIP_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


def sanitize_export_name(name: str, max_len: int = 80) -> str:
    """清理为可用文件/文件夹名。"""
    name = _MC_FORMAT.sub("", name or "")
    name = _INVALID_WIN.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "unnamed_mod"
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name or "unnamed_mod"


def base_mod_name(name: str) -> str:
    """去掉已有本地化署名后缀，得到模组基名。"""
    return strip_credit_suffix(name or "") or name or "unnamed_mod"


def _should_skip(path: Path) -> bool:
    if path.name.casefold() in _SKIP_NAMES:
        return True
    if path.name.endswith(".backup"):
        return True
    if "_backup" in path.parts:
        return True
    return False


def _add_pack_to_zip(zf: zipfile.ZipFile, pack_dir: Path, arc_prefix: str | None, log):
    """
    把包目录写入 zip。
    arc_prefix 为 None：内容在 zip 根（.mcpack）；
    否则写入 prefix/相对路径（.mcaddon 内的 BP/RP 文件夹）。
    """
    count = 0
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file() or _should_skip(path):
            continue
        rel = path.relative_to(pack_dir).as_posix()
        arcname = rel if arc_prefix is None else f"{arc_prefix}/{rel}"
        zf.write(path, arcname)
        count += 1
    log(f"  已打包 {pack_dir.name} → {arc_prefix or '(根目录)'}（{count} 个文件）")
    return count


def build_export_filename(
    mod_name: str, credit: str, both: bool, code: str | None = None
) -> str:
    titled = sanitize_export_name(
        with_credit(base_mod_name(mod_name), credit, code or DEFAULT_CODE)
    )
    return f"{titled}.mcaddon" if both else f"{titled}.mcpack"


def export_localized_pack(
    out_dir: Path,
    mod_name: str,
    credit: str,
    rp: Path | None,
    bp: Path | None,
    log,
    code: str | None = None,
) -> Path:
    """
    导出当前模组：
    - RP+BP → 模组名+署名.mcaddon，内含 模组名BP / 模组名RP
    - 仅一侧 → 模组名+署名.mcpack（包内容在 zip 根目录）
    """
    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    has_rp = rp is not None and Path(rp).is_dir()
    has_bp = bp is not None and Path(bp).is_dir()
    if not has_rp and not has_bp:
        raise ValueError("没有可导出的资源包或行为包")

    base = sanitize_export_name(base_mod_name(mod_name))
    both = has_rp and has_bp
    filename = build_export_filename(base, credit, both, code)
    dest = out_dir / filename
    if dest.exists():
        dest.unlink()

    log(f"导出目标: {dest}")
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if both:
            log("格式: .mcaddon（ZIP，内含 BP / RP 文件夹）")
            _add_pack_to_zip(zf, Path(bp), f"{base}BP", log)
            _add_pack_to_zip(zf, Path(rp), f"{base}RP", log)
        else:
            pack = Path(bp if has_bp else rp)
            kind = "行为包" if has_bp else "资源包"
            log(f"格式: .mcpack（ZIP，{kind}内容在根目录）")
            _add_pack_to_zip(zf, pack, None, log)

    size_kb = dest.stat().st_size // 1024
    log(f"导出完成: {dest.name}（{size_kb} KB）")
    return dest
