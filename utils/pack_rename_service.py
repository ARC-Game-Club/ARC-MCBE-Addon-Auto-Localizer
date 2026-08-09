# -*- coding: utf-8 -*-
"""按 manifest / 语言文件中的包名，整理资源包与行为包文件夹名称。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .lang_files import parse_lang_content
from .paths import get_minecraft_base_dir

PACK_ROOT_SUFFIXES = (
    ("behavior_packs", "BP"),
    ("development_behavior_packs", "BP"),
    ("resource_packs", "RP"),
    ("development_resource_packs", "RP"),
)

_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MC_FORMAT_CODES = re.compile(r"§.")
_WHITESPACE = re.compile(r"\s+")
_SUFFIX_RE = re.compile(r"(?:\s*[\[(_-]?\s*(BP|RP)\s*[\])]?)$", re.IGNORECASE)


@dataclass
class RenamePlan:
    src: Path
    dest: Path
    display_name: str
    suffix: str
    skipped: bool = False
    reason: str = ""

    @property
    def changed(self) -> bool:
        return (not self.skipped) and self.src.resolve() != self.dest.resolve()


def get_pack_roots(base_dir: Path | None = None) -> list[tuple[Path, str]]:
    """返回 [(包根目录, BP|RP), ...]。"""
    base = Path(base_dir) if base_dir else get_minecraft_base_dir()
    roots = []
    for folder, suffix in PACK_ROOT_SUFFIXES:
        path = base / folder
        if path.is_dir():
            roots.append((path, suffix))
    return roots


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def _read_lang_key(lang_file: Path, key: str) -> str | None:
    """从单个 .lang 读取 key 的值。"""
    if not lang_file.is_file():
        return None
    try:
        content = lang_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    for kind, k, value in parse_lang_content(content):
        if kind == "entry" and k == key and value is not None:
            value = value.strip()
            return value or None
    return None


def _lookup_lang_value(texts_dir: Path, key: str) -> str | None:
    """读取语言文件中的 key；优先 zh_CN，再按 languages.json / 其它 .lang。"""
    # 1) 中文优先
    for zh_name in ("zh_CN.lang", "zh_cn.lang"):
        value = _read_lang_key(texts_dir / zh_name, key)
        if value:
            return value

    # 2) languages.json 顺序（跳过已试过的 zh_CN）
    seen = {texts_dir / "zh_CN.lang", texts_dir / "zh_cn.lang"}
    langs_path = texts_dir / "languages.json"
    if langs_path.is_file():
        langs = _read_json(langs_path)
        if isinstance(langs, list):
            for item in langs:
                code = str(item).strip()
                if not code:
                    continue
                lang_file = texts_dir / f"{code}.lang"
                if lang_file in seen:
                    continue
                seen.add(lang_file)
                value = _read_lang_key(lang_file, key)
                if value:
                    return value

    # 3) 剩余任意 .lang
    for lang_file in sorted(texts_dir.glob("*.lang")):
        if lang_file in seen:
            continue
        value = _read_lang_key(lang_file, key)
        if value:
            return value
    return None


def resolve_pack_display_name(pack_dir: Path) -> tuple[str | None, str]:
    """
    从包目录解析展示名（中文优先）。
    优先级：zh_CN.lang pack.name → 其它 .lang pack.name → manifest.header.name
    返回 (name, error)；成功时 error 为空字符串。
    """
    texts_dir = pack_dir / "texts"
    if texts_dir.is_dir():
        resolved = _lookup_lang_value(texts_dir, "pack.name")
        if resolved:
            return resolved, ""

    manifest = pack_dir / "manifest.json"
    if not manifest.is_file():
        return None, "无 manifest.json"
    data = _read_json(manifest)
    if not isinstance(data, dict):
        return None, "manifest 解析失败"
    header = data.get("header") or {}
    raw_name = header.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None, "manifest 无 name"
    raw_name = raw_name.strip()
    if raw_name == "pack.name":
        return None, "未能从 .lang 解析 pack.name"
    return raw_name, ""


def infer_pack_suffix(pack_dir: Path) -> str | None:
    """根据父目录名推断 BP / RP。"""
    parent = Path(pack_dir).parent.name
    for folder, suffix in PACK_ROOT_SUFFIXES:
        if parent == folder:
            return suffix
    return None


def plan_rename_for_pack(pack_dir: Path) -> RenamePlan:
    """为单个包目录生成重命名计划。"""
    pack_dir = Path(pack_dir)
    suffix = infer_pack_suffix(pack_dir)
    if not suffix:
        return RenamePlan(
            src=pack_dir,
            dest=pack_dir,
            display_name="",
            suffix="?",
            skipped=True,
            reason="不在标准包目录下",
        )
    display, err = resolve_pack_display_name(pack_dir)
    if err:
        return RenamePlan(
            src=pack_dir,
            dest=pack_dir,
            display_name="",
            suffix=suffix,
            skipped=True,
            reason=err,
        )
    safe = sanitize_folder_name(display)
    final_name = ensure_pack_suffix(safe, suffix)
    dest = _unique_dest(pack_dir.parent, final_name, pack_dir)
    return RenamePlan(
        src=pack_dir,
        dest=dest,
        display_name=display,
        suffix=suffix,
    )


def sync_mod_pack_folder_names(rp: Path | None, bp: Path | None, config, log) -> int:
    """
    按当前（优先中文）包名重命名 RP/BP 文件夹，并回写 config 路径与模组名。
    返回成功重命名个数。
    """
    plans = []
    for path in (rp, bp):
        if path is None:
            continue
        p = Path(path)
        if p.is_dir():
            plans.append(plan_rename_for_pack(p))
    changes = [p for p in plans if (not p.skipped) and p.changed]
    if not changes:
        if plans and all(p.skipped for p in plans):
            for p in plans:
                if p.reason:
                    log(f"跳过重命名 {p.src.name}: {p.reason}")
        else:
            log("文件夹名称已是最新，无需重命名")
        return 0

    for plan in changes:
        log(f"重命名: {plan.src.name} → {plan.dest.name}")
    ok, errors = apply_pack_renames(changes)
    for err in errors:
        log(f"重命名失败: {err}")
    if ok:
        # 回写配置路径
        if config is not None:
            old_rp = config.get("resource_pack_path")
            old_bp = config.get("behavior_pack_path")
            new_rp = remap_path_after_rename(old_rp, changes)
            new_bp = remap_path_after_rename(old_bp, changes)
            if new_rp != old_rp:
                config.set(new_rp, "resource_pack_path")
            if new_bp != old_bp:
                config.set(new_bp, "behavior_pack_path")
            # 模组展示名：取第一个成功计划的 display_name（已含署名）
            for plan in changes:
                if plan.display_name:
                    config.set(plan.display_name, "current_mod_name")
                    break
            config.save()
        log(f"已按中文包名更新 {ok} 个文件夹")
    return ok


def sanitize_folder_name(name: str, max_len: int = 80) -> str:
    """清理为 Windows 可用文件夹名。"""
    name = _MC_FORMAT_CODES.sub("", name)
    name = _INVALID_WIN_CHARS.sub("", name)
    name = _WHITESPACE.sub(" ", name).strip(" .")
    if not name:
        name = "unnamed_pack"
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name or "unnamed_pack"


def ensure_pack_suffix(name: str, suffix: str) -> str:
    """确保名称以 BP / RP 结尾（避免重复追加）。"""
    suffix = suffix.upper()
    m = _SUFFIX_RE.search(name)
    if m and m.group(1).upper() == suffix:
        # 统一成「名字 BP」形式
        base = name[: m.start()].rstrip(" .")
        return f"{base} {suffix}" if base else suffix
    return f"{name} {suffix}"


def _unique_dest(parent: Path, folder_name: str, src: Path) -> Path:
    candidate = parent / folder_name
    if not candidate.exists() or candidate.resolve() == src.resolve():
        return candidate
    index = 2
    while True:
        alt = parent / f"{folder_name}_{index}"
        if not alt.exists() or alt.resolve() == src.resolve():
            return alt
        index += 1


def plan_pack_renames(base_dir: Path | None = None) -> list[RenamePlan]:
    """扫描标准包目录，生成重命名计划。"""
    plans: list[RenamePlan] = []
    for root, suffix in get_pack_roots(base_dir):
        for pack_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not pack_dir.is_dir():
                continue
            display, err = resolve_pack_display_name(pack_dir)
            if err:
                plans.append(
                    RenamePlan(
                        src=pack_dir,
                        dest=pack_dir,
                        display_name="",
                        suffix=suffix,
                        skipped=True,
                        reason=err,
                    )
                )
                continue
            safe = sanitize_folder_name(display)
            final_name = ensure_pack_suffix(safe, suffix)
            dest = _unique_dest(root, final_name, pack_dir)
            plans.append(
                RenamePlan(
                    src=pack_dir,
                    dest=dest,
                    display_name=display,
                    suffix=suffix,
                )
            )
    return plans


def apply_pack_renames(plans: list[RenamePlan]) -> tuple[int, list[str]]:
    """执行重命名（两阶段，避免目标名互相占用），返回 (成功数, 错误列表)。"""
    pending = [p for p in plans if (not p.skipped) and p.changed]
    if not pending:
        return 0, []

    errors: list[str] = []
    temp_moves: list[tuple[RenamePlan, Path]] = []
    for index, plan in enumerate(pending):
        if not plan.src.exists():
            errors.append(f"源不存在: {plan.src}")
            continue
        temp = plan.src.parent / f"__mcbe_rename_tmp_{index}_{plan.src.name}"
        # 极端情况下临时名仍冲突
        n = 0
        while temp.exists():
            n += 1
            temp = plan.src.parent / f"__mcbe_rename_tmp_{index}_{n}_{plan.src.name}"
        try:
            plan.src.rename(temp)
            temp_moves.append((plan, temp))
        except OSError as exc:
            errors.append(f"{plan.src.name} → (临时名): {exc}")

    ok = 0
    for plan, temp in temp_moves:
        dest = plan.dest
        if dest.exists():
            # 再找一个空位，避免半成品残留
            dest = _unique_dest(plan.dest.parent, plan.dest.name, temp)
            plan.dest = dest
        try:
            temp.rename(dest)
            ok += 1
        except OSError as exc:
            errors.append(f"{plan.src.name} → {dest.name}: {exc}")
            # 尽量还原
            try:
                if temp.exists() and not plan.src.exists():
                    temp.rename(plan.src)
            except OSError:
                pass
    return ok, errors


def remap_path_after_rename(path: str, plans: list[RenamePlan]) -> str:
    """若当前选中路径被重命名，返回新路径。"""
    text = (path or "").strip()
    if not text:
        return text
    try:
        current = Path(text).resolve()
    except OSError:
        return text
    for plan in plans:
        if plan.skipped or not plan.changed:
            continue
        try:
            if current == plan.src.resolve():
                return str(plan.dest)
        except OSError:
            continue
    return text
