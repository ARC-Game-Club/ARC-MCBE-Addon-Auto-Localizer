# -*- coding: utf-8 -*-
""".lang 语言文件与 languages.json 的处理。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .languages import DEFAULT_CODE
from .text_utils import needs_translation


def ensure_language_in_languages(texts_dir: Path, code: str, log) -> bool:
    """确保 texts/languages.json 中包含目标语言码，不存在则创建。"""
    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    lang_json = texts_dir / "languages.json"
    if lang_json.exists():
        try:
            langs = json.loads(lang_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log(f"读取 languages.json 失败: {e}")
            return False
        if not isinstance(langs, list):
            log("languages.json 格式不正确（不是数组）")
            return False
        if code in langs:
            log(f"languages.json 已包含 {code}，无需修改")
            return True
        langs.append(code)
        try:
            lang_json.write_text(
                json.dumps(langs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log(f"已在 languages.json 中添加 {code}: {langs}")
            return True
        except OSError as e:
            log(f"写入 languages.json 失败: {e}")
            return False
    existing = sorted(f.stem for f in texts_dir.glob("*.lang"))
    langs = existing if existing else ["en_US"]
    if code not in langs:
        langs.append(code)
    try:
        lang_json.write_text(
            json.dumps(langs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"已创建 languages.json: {langs}")
        return True
    except OSError as e:
        log(f"写入 languages.json 失败: {e}")
        return False


# 兼容旧名
def ensure_zh_cn_in_languages(texts_dir: Path, log) -> bool:
    return ensure_language_in_languages(texts_dir, "zh_CN", log)


def find_base_lang(texts_dir: Path, target_code: str | None = None):
    """返回用于复制的基础 .lang 文件路径（优先 en_US，否则第一个非目标语言的）。"""
    target_code = (target_code or DEFAULT_CODE).strip() or DEFAULT_CODE
    if not texts_dir.is_dir():
        return None
    files = sorted(texts_dir.glob("*.lang"))
    for f in files:
        if f.stem == "en_US":
            return f
    for f in files:
        if f.stem != target_code:
            return f
    return None


def copy_lang_to_target(texts_dir: Path, code: str, log) -> Path | None:
    """复制基础语言文件为目标语言 .lang，返回目标路径。"""
    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    src = find_base_lang(texts_dir, code)
    if src is None:
        log("未找到可用的语言文件 (.lang)，请手动放入 en_US.lang")
        return None
    dst = texts_dir / f"{code}.lang"
    if dst.exists():
        log(f"{code}.lang 已存在，跳过复制（如需重新翻译请先删除）")
        return dst
    try:
        shutil.copy2(src, dst)
        log(f"已复制 {src.name} → {code}.lang")
        return dst
    except OSError as e:
        log(f"复制失败: {e}")
        return None


def copy_lang_to_zh_cn(texts_dir: Path, log) -> Path | None:
    return copy_lang_to_target(texts_dir, "zh_CN", log)


def ensure_texts_dir(pack_dir: Path, target_code: str, log) -> Path | None:
    """
    确保包内有 texts/、en_US.lang、languages.json，以及目标语言条目。
    返回 texts 目录；失败返回 None。
    """
    pack_dir = Path(pack_dir)
    target_code = (target_code or DEFAULT_CODE).strip() or DEFAULT_CODE
    texts = pack_dir / "texts"
    try:
        texts.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log(f"创建 texts/ 失败: {e}")
        return None

    en_us = texts / "en_US.lang"
    if not en_us.is_file():
        # 若已有其它 .lang，优先复制一份作 en_US；否则建空文件
        other = find_base_lang(texts, target_code)
        if other is not None and other.resolve() != en_us.resolve():
            try:
                shutil.copy2(other, en_us)
                log(f"已从 {other.name} 创建 en_US.lang")
            except OSError as e:
                log(f"创建 en_US.lang 失败: {e}")
                return None
        else:
            try:
                en_us.write_text("", encoding="utf-8")
                log("已创建空的 en_US.lang")
            except OSError as e:
                log(f"创建 en_US.lang 失败: {e}")
                return None

    if not ensure_language_in_languages(texts, target_code, log):
        return None
    # 确保 languages.json 也有 en_US
    ensure_language_in_languages(texts, "en_US", log)
    return texts


def parse_lang_content(content: str):
    """
    解析 .lang 内容为 [(kind, key, value)]：
      kind: "entry" | "comment" | "empty"
    entry 只保留第一次 '=' 分割的键值。
    """
    parsed = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            parsed.append(("empty", None, None))
        elif stripped.startswith("##"):
            parsed.append(("comment", None, None))
        elif "=" in stripped:
            key, value = stripped.split("=", 1)
            parsed.append(("entry", key.strip(), value))
        else:
            parsed.append(("comment", None, None))
    return parsed


def read_lang_map(lang_path: Path) -> dict[str, str]:
    """读取 .lang 为 {key: value}；文件不存在返回空 dict。"""
    lang_path = Path(lang_path)
    if not lang_path.is_file():
        return {}
    try:
        content = lang_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return {}
    out: dict[str, str] = {}
    for kind, key, value in parse_lang_content(content):
        if kind == "entry" and key is not None and key not in out:
            out[key] = value if value is not None else ""
    return out


def upsert_lang_entries(lang_path: Path, mapping: dict[str, str], log) -> int:
    """
    把 mapping 中缺失的 key 追加到 .lang；已有 key 不覆盖。
    返回新追加条数。
    """
    lang_path = Path(lang_path)
    if not mapping:
        return 0
    existing = read_lang_map(lang_path)
    to_add = {k: v for k, v in mapping.items() if k not in existing}
    if not to_add:
        return 0
    try:
        if lang_path.is_file():
            content = lang_path.read_text(encoding="utf-8-sig")
        else:
            content = ""
            lang_path.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, UnicodeError) as e:
        log(f"读取 {lang_path.name} 失败: {e}")
        return 0

    lines = []
    if content and not content.endswith("\n"):
        lines.append("")
    for key, value in to_add.items():
        lines.append(f"{key}={value}")
    new_content = content + ("\n".join(lines) + "\n" if lines else "")
    # 若原文件为空且 lines 以空行开头，去掉开头空行
    if not content:
        new_content = "\n".join(f"{k}={v}" for k, v in to_add.items()) + "\n"
    try:
        lang_path.write_text(new_content, encoding="utf-8")
    except OSError as e:
        log(f"写入 {lang_path.name} 失败: {e}")
        return 0
    log(f"已向 {lang_path.name} 追加 {len(to_add)} 条")
    return len(to_add)


def sync_missing_keys_from_en_us(texts_dir: Path, code: str, log) -> int:
    """
    将 en_US.lang 中有而目标 .lang 中没有的 key 复制过去（值为英文源），
    便于后续翻译步骤处理 pack.name 等遗漏条目。
    """
    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    texts_dir = Path(texts_dir)
    en_us = texts_dir / "en_US.lang"
    target = texts_dir / f"{code}.lang"
    if not en_us.is_file() or not target.is_file():
        return 0
    en_map = read_lang_map(en_us)
    target_map = read_lang_map(target)
    missing = {k: v for k, v in en_map.items() if k not in target_map}
    if not missing:
        return 0
    n = upsert_lang_entries(target, missing, log)
    if n:
        log(f"  从 en_US 补全 {n} 条缺失 key（含 pack.name 等）")
    return n


def rebuild_lang_lines(orig_text: str, parsed, translated: dict) -> str:
    """基于原始文本重建，entry 行用翻译值替换 value，保留末尾换行。"""
    out = []
    for line, (kind, key, value) in zip(orig_text.splitlines(), parsed):
        if kind == "entry" and key in translated and translated[key] != value:
            out.append(f"{key}={translated[key]}")
        else:
            out.append(line)
    result = "\n".join(out)
    if orig_text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def lang_file_needs_translation(lang_path: Path, target_code: str | None = None) -> bool:
    """粗略判断 .lang 文件是否仍含待翻译条目。"""
    try:
        content = lang_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(
        needs_translation(value, target_code)
        for kind, _key, value in parse_lang_content(content)
        if kind == "entry"
    )
