# -*- coding: utf-8 -*-
""".lang 语言文件与 languages.json 的处理。"""
import json
import shutil
from pathlib import Path

from .text_utils import is_english_text


def ensure_zh_cn_in_languages(texts_dir: Path, log) -> bool:
    """确保 texts/languages.json 中包含 zh_CN，不存在则创建。"""
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
        if "zh_CN" in langs:
            log("languages.json 已包含 zh_CN，无需修改")
            return True
        langs.append("zh_CN")
        try:
            lang_json.write_text(
                json.dumps(langs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log(f"已在 languages.json 中添加 zh_CN: {langs}")
            return True
        except OSError as e:
            log(f"写入 languages.json 失败: {e}")
            return False
    # 不存在则创建：扫描已有 .lang 文件推断语言列表
    existing = sorted(f.stem for f in texts_dir.glob("*.lang"))
    langs = existing if existing else ["en_US"]
    if "zh_CN" not in langs:
        langs.append("zh_CN")
    try:
        lang_json.write_text(
            json.dumps(langs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"已创建 languages.json: {langs}")
        return True
    except OSError as e:
        log(f"写入 languages.json 失败: {e}")
        return False


def find_base_lang(texts_dir: Path):
    """返回用于复制的基础 .lang 文件路径（优先 en_US，否则第一个非 zh_CN 的）。"""
    if not texts_dir.is_dir():
        return None
    files = sorted(texts_dir.glob("*.lang"))
    for f in files:
        if f.stem == "en_US":
            return f
    for f in files:
        if f.stem != "zh_CN":
            return f
    return None


def copy_lang_to_zh_cn(texts_dir: Path, log) -> Path | None:
    """复制基础语言文件为 zh_CN.lang，返回目标路径。"""
    src = find_base_lang(texts_dir)
    if src is None:
        log("未找到可用的语言文件 (.lang)，请手动放入 en_US.lang")
        return None
    dst = texts_dir / "zh_CN.lang"
    if dst.exists():
        log("zh_CN.lang 已存在，跳过复制（如需重新翻译请先删除）")
        return dst
    try:
        shutil.copy2(src, dst)
        log(f"已复制 {src.name} → zh_CN.lang")
        return dst
    except OSError as e:
        log(f"复制失败: {e}")
        return None


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


def lang_file_needs_translation(lang_path: Path) -> bool:
    """粗略判断 .lang 文件是否仍含待翻译的英文条目。"""
    try:
        content = lang_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(
        is_english_text(value)
        for kind, _key, value in parse_lang_content(content)
        if kind == "entry"
    )
