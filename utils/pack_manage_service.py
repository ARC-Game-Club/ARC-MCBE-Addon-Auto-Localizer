# -*- coding: utf-8 -*-
"""模组包管理：资源管理器定位、移入 development_* 目录、删除模组。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# 官方目录 → 开发目录（同名同级，便于即改即测）
OFFICIAL_TO_DEV = {
    "resource_packs": "development_resource_packs",
    "behavior_packs": "development_behavior_packs",
}


def _path_key(path: Path | str) -> str:
    """Windows 下忽略大小写的稳定路径比较键。"""
    return os.path.normcase(os.path.abspath(str(path)))


def open_folder(path: Path | str) -> None:
    """直接进入并打开该文件夹（资源管理器定位到目录本身）。"""
    target = Path(path)
    if not target.is_dir():
        raise FileNotFoundError(f"目录不存在: {target}")
    os.startfile(str(target))  # noqa: S606 - 仅本地打开目录


def plan_dev_move(pack_dir: Path | str) -> Path | None:
    """若包在官方 resource_packs / behavior_packs 下，返回对应 development_* 目标根目录；否则 None。"""
    pack_dir = Path(pack_dir)
    dev_name = OFFICIAL_TO_DEV.get(pack_dir.parent.name.lower())
    if dev_name is None:
        return None
    # development_* 与官方目录同级（都在 com.mojang 下）
    return pack_dir.parent.parent / dev_name


def _unique_dest(parent: Path, folder_name: str, src: Path) -> Path:
    candidate = parent / folder_name
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        alt = parent / f"{folder_name}_{index}"
        if not alt.exists():
            return alt
        index += 1


def move_pack_to_development(pack_dir: Path | str) -> tuple[Path | None, str]:
    """把单个包移入同级 development_* 目录（重名自动加序号）。

    返回 (新路径, 错误)。无需移动时返回 (None, "")；失败返回 (None, 错误信息)。
    """
    pack_dir = Path(pack_dir)
    dest_root = plan_dev_move(pack_dir)
    if dest_root is None:
        return None, ""
    if not pack_dir.is_dir():
        return None, f"目录不存在: {pack_dir}"
    try:
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = _unique_dest(dest_root, pack_dir.name, pack_dir)
        shutil.move(str(pack_dir), str(dest))
        return dest, ""
    except OSError as exc:
        return None, str(exc)


def move_mod_packs_to_development(
    rp: Path | str | None,
    bp: Path | str | None,
    config=None,
    log=None,
) -> tuple[bool, str, str]:
    """把当前模组在官方目录下的 RP/BP 移入 development_*，并回写 config 路径。

    返回 (是否有移动, 新RP路径, 新BP路径)。
    """
    emit = log or (lambda _msg: None)
    moved = False
    new_rp = str(rp) if rp else ""
    new_bp = str(bp) if bp else ""
    for label, path in (("资源包", rp), ("行为包", bp)):
        if not path:
            continue
        dest, err = move_pack_to_development(path)
        if err:
            emit(f"{label}移入开发目录失败: {err}")
            continue
        if dest is None:
            continue
        emit(f"{label}已移入开发目录: {dest.parent.name}/{dest.name}")
        if label == "资源包":
            new_rp = str(dest)
        else:
            new_bp = str(dest)
        moved = True
    if moved and config is not None:
        if new_rp:
            config.set(new_rp, "resource_pack_path")
        if new_bp:
            config.set(new_bp, "behavior_pack_path")
        config.save()
    return moved, new_rp, new_bp


def delete_pack_dirs(paths: list[Path | str]) -> tuple[int, list[str]]:
    """递归删除包目录，返回 (成功数, 错误列表)。"""
    ok = 0
    errors: list[str] = []
    for raw in paths:
        p = Path(raw)
        if not p.is_dir():
            continue
        try:
            shutil.rmtree(p)
            ok += 1
        except OSError as exc:
            errors.append(f"{p.name}: {exc}")
    return ok, errors


def prune_config_selection(config, deleted: list[Path | str]) -> bool:
    """删除的目录若正是当前选中模组的包，清空配置选择。返回是否清空过。"""
    gone = {_path_key(p) for p in deleted}
    hit = False
    for key in ("resource_pack_path", "behavior_pack_path"):
        val = str(config.get(key) or "").strip()
        if val and _path_key(val) in gone:
            config.set("", key)
            hit = True
    if hit:
        config.set("", "current_mod_name")
        config.save()
    return hit
