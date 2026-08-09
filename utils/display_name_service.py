# -*- coding: utf-8 -*-
"""display_name 的提取、翻译与应用。

底层解析 / 更新逻辑复用 ui.display_name_tool_gui。
"""
import json
import shutil
from pathlib import Path

from ui.display_name_tool_gui import (
    find_json_files,
    find_display_name_recursive,
    load_mapping,
    update_display_name_recursive,
    scan_mods,
)

from .llm_service import translate_text

DISPLAY_NAME_TRANSLATE_PROMPT = """你是一名 Minecraft 基岩版模组汉化专家。
下面是提取出的 display_name 汉化映射，每行格式为：相对路径=JSON字符串字面量。
请把每个等号右边的显示名翻译成简体中文，输出保持原格式（相对路径=JSON字符串），
只改值不改键。注意值需要用 JSON 字符串语法（引号包裹，转义 \\n、§ 颜色码等保留）。
直接输出全部翻译结果，不要任何解释。

内容：
{content}
"""


def extract_display_names(root: Path, output_path: Path):
    """提取目录下所有 display_name 到映射文件，返回 (扫描数, 找到数)。"""
    lines, processed, found = [], 0, 0
    for fp in find_json_files(root):
        processed += 1
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        value = find_display_name_recursive(data)
        if value is None:
            continue
        found += 1
        rel = str(fp.relative_to(root))
        lines.append(f"{rel}={json.dumps(value, ensure_ascii=False)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return processed, found


def translate_display_name_map(map_path: Path, llm_cfg, log) -> int:
    """用 LLM 翻译 display_name 映射文件，返回结果行数。"""
    mapping = load_mapping(map_path)
    if not mapping:
        log("映射为空")
        return 0
    content = map_path.read_text(encoding="utf-8")
    out = translate_text(llm_cfg, DISPLAY_NAME_TRANSLATE_PROMPT.format(content=content), log)
    result_lines = []
    for line in out.splitlines():
        if "=" in line:
            result_lines.append(line)
    if not result_lines:
        log("LLM 未返回有效结果")
        return 0
    covered = {ln.split("=", 1)[0] for ln in result_lines}
    for k, v in mapping.items():
        if k not in covered:
            result_lines.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
    backup = map_path.with_suffix(".txt.orig")
    shutil.copy2(str(map_path), str(backup))
    map_path.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    return len(result_lines)


def apply_display_name_map(root: Path, map_path: Path, log):
    """应用映射到 JSON 文件，返回 (更新数, 跳过数, 未找到数)。"""
    mapping = load_mapping(map_path)
    log(f"加载 {len(mapping)} 条映射")
    updated = skipped = not_found = 0
    for rel, new_value in mapping.items():
        fp = root / rel
        if not fp.exists():
            not_found += 1
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            skipped += 1
            log(f"跳过: {rel} ({e})")
            continue
        if update_display_name_recursive(data, new_value):
            text = json.dumps(data, ensure_ascii=False, indent=2)
            if not text.endswith("\n"):
                text += "\n"
            fp.write_text(text, encoding="utf-8")
            updated += 1
        else:
            skipped += 1
    return updated, skipped, not_found
