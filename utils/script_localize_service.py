# -*- coding: utf-8 -*-
"""行为包脚本提示字符串汉化。

针对 sendMessage / form.title|button|label|body|toggle|… / setActionBar|setTitle|setSubtitle
以及选项里的 tooltip/placeholderText 等字符串字面量，调用 LLM 只改提示文字，
保留 § 颜色码、占位符与 ${} 插值。语言键引用（无空格的 a.b.c）与复杂多行模板跳过。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .llm_service import translate_text
from .text_utils import is_english_text

SCRIPT_EXTENSIONS = {".js", ".ts", ".mjs", ".cjs"}

# 本机行为包统计得到的主要玩家可见提示 API / 表单控件
TIP_METHOD_RE = re.compile(
    r"\.(?:sendMessage|setActionBar|setTitle|setSubtitle|"
    r"title|button|label|body|"
    r"toggle|slider|dropdown|textField|divider|header|submitButton)\s*\(",
    re.M,
)

# ModalForm 等选项对象里的玩家可见文案字段
TIP_PROP_RE = re.compile(
    r"\b(?:tooltip|placeholderText|placeholder)\s*:",
    re.M,
)

# 疑似语言文件键：foo.bar / pack.ui.toggle_x（无空格、无 §）
_LANG_KEY_RE = re.compile(r"^[A-Za-z][\w]*(\.[\w]+)+$")

# 插值里出现这些 → 当作代码表达式，不翻译
_COMPLEX_CODE_MARKERS = (
    ".map",
    ".join",
    ".filter",
    ".forEach",
    ".reduce",
    ".flatMap",
    "=>",
    "function",
    "\n",
    "\r",
)

SCRIPT_TRANSLATE_PROMPT = """你是 Minecraft 基岩版模组脚本汉化专家。
下面是从 JS/TS 脚本中提取的玩家可见提示字符串（JSON 数组），请译为简体中文。

规则：
1. 只翻译人类可读文字；不要改动代码结构
2. 完整保留 § 及后续格式/颜色码（如 §c、§l、§r）、\\n、\\t
3. 完整保留 ${...} 模板插值、%s、%1$s、{{...}} 等占位符，位置与内容都不要改
4. 已是中文或纯符号的保持原样
5. 只返回 JSON 数组，每项格式 {"id":"S0000","text":"译文"}，id 与输入一致，不要其它说明

待翻译：
__BATCH__
"""

_SKIP_PREFIXES = (
    "textures/",
    "texture/",
    "http://",
    "https://",
    "minecraft:",
    "data:",
)


def iter_script_files(root: Path):
    root = Path(root)
    if not root.is_dir():
        return
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in SCRIPT_EXTENSIONS:
            continue
        if "node_modules" in fp.parts or "_backup" in fp.parts:
            continue
        yield fp


def _skip_line_comment(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i] not in "\r\n":
        i += 1
    return i


def _skip_block_comment(text: str, i: int) -> int:
    j = text.find("*/", i)
    return len(text) if j < 0 else j + 2


def _skip_template_interpolation(text: str, i: int) -> int:
    """
    i 指向 '${' 之后的 '{'。返回匹配 '}' 之后的下标。
    插值内的嵌套字符串/模板会正确跳过，避免把字符串里的 } 当成结束。
    """
    n = len(text)
    if i >= n or text[i] != "{":
        return i
    i += 1
    depth = 1
    while i < n and depth:
        ch = text[i]
        if ch in "'\"`":
            nested = _parse_string_literal(text, i)
            if nested:
                _content, _c0, c1, _q = nested
                i = c1 + 1
                continue
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i = _skip_line_comment(text, i + 2)
                continue
            if nxt == "*":
                i = _skip_block_comment(text, i + 2)
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return i


def _parse_string_literal(text: str, start: int) -> tuple[str, int, int, str] | None:
    """
    从 start 起跳过空白，解析一个字符串字面量。
    返回 (内容, 内容起始下标, 内容结束下标(不含), 引号类型)，失败返回 None。
    """
    i = start
    n = len(text)
    while i < n and text[i] in " \t\r\n":
        i += 1
    if i >= n:
        return None
    quote = text[i]
    if quote not in "'\"`":
        return None
    i += 1
    content_start = i
    escaped = False
    while i < n:
        ch = text[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\" and quote != "`":
            escaped = True
            i += 1
            continue
        if quote == "`" and ch == "\\":
            if i + 1 < n and text[i + 1] in "\\`$":
                i += 2
                continue
        if quote == "`" and ch == "$" and i + 1 < n and text[i + 1] == "{":
            i = _skip_template_interpolation(text, i + 1)
            continue
        if ch == quote:
            return text[content_start:i], content_start, i, quote
        i += 1
    return None


def _interpolation_bodies(s: str) -> list[str]:
    """提取字符串内容中各 ${...} 的内部文本（不含花括号）。"""
    bodies: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "$" and i + 1 < n and s[i + 1] == "{":
            start = i + 2
            end = _skip_template_interpolation(s, i + 1)
            # end 在匹配 } 之后；body 为 start .. end-1 不含 }
            if end > start:
                bodies.append(s[start : end - 1])
            i = end
            continue
        i += 1
    return bodies


def _is_simple_interpolation_body(body: str) -> bool:
    """只允许标识符/属性链/简单下标，例如 name、player.name、items[0]。"""
    b = body.strip()
    if not b:
        return False
    for m in _COMPLEX_CODE_MARKERS:
        if m in b:
            return False
    if any(tok in b for tok in ("(", "{", "`", "?", ":", ";", "=")):
        return False
    # 允许 a.b.c / a[0] / a['x'] 太宽，这里禁止引号，只留 [数字]
    if not re.fullmatch(r"[A-Za-z_$][\w.$]*(?:\[\d+\])?", b):
        return False
    return True


def _looks_like_lang_key(s: str) -> bool:
    """无空格的 a.b.c 形态，多半是 translate 键而非直接展示文案。"""
    t = s.strip()
    if " " in t or "\t" in t or "§" in t or "${" in t:
        return False
    return bool(_LANG_KEY_RE.fullmatch(t))


def _should_translate(s: str) -> bool:
    s = s.strip()
    if len(s) < 2:
        return False
    low = s.lower()
    for p in _SKIP_PREFIXES:
        if low.startswith(p):
            return False
    if "/" in s and " " not in s and "§" not in s:
        return False
    if _looks_like_lang_key(s):
        return False
    if not is_english_text(s):
        return False
    return True


def _is_safe_tip_string(s: str) -> bool:
    """
    可安全送去翻译的提示串。
    多行、嵌套反引号、或 ${} 内含 map/join/箭头函数等代码表达式 → 跳过。
    """
    if not _should_translate(s):
        return False
    # 多行：旧行协议会截断；即便改 JSON 也常是「文案+代码」混合，风险高
    if "\n" in s or "\r" in s:
        return False
    # 内容里再出现反引号 = 模板套模板
    if "`" in s:
        return False
    if "${" in s:
        for body in _interpolation_bodies(s):
            if not _is_simple_interpolation_body(body):
                return False
        # 解析失败导致没提出 body，但字面有 ${ → 保守跳过
        if not _interpolation_bodies(s):
            return False
    return True


def extract_tip_strings(source: str) -> list[tuple[int, int, str]]:
    """
    提取脚本中提示调用的首个字符串实参，以及 tooltip 等选项字段。
    返回 [(内容起始, 内容结束, 原文内容), ...]，按出现顺序；同位置不重复。
    """
    hits: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int]] = set()

    def add(c0: int, c1: int, content: str) -> None:
        key = (c0, c1)
        if key in seen_spans:
            return
        if not _is_safe_tip_string(content):
            return
        seen_spans.add(key)
        hits.append((c0, c1, content))

    for m in TIP_METHOD_RE.finditer(source):
        parsed = _parse_string_literal(source, m.end())
        if not parsed:
            continue
        content, c0, c1, _quote = parsed
        add(c0, c1, content)

    for m in TIP_PROP_RE.finditer(source):
        parsed = _parse_string_literal(source, m.end())
        if not parsed:
            continue
        content, c0, c1, _quote = parsed
        add(c0, c1, content)

    hits.sort(key=lambda x: x[0])
    return hits


def _parse_llm_json_batch(out: str, id_map: dict[str, str]) -> dict[str, str]:
    """从 LLM 输出解析 {原文: 译文}。优先 JSON，回退 ID=行协议。"""
    got: dict[str, str] = {}
    text = (out or "").strip()
    if not text:
        return got

    # 尝试截取首个 JSON 数组
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            arr = json.loads(text[start : end + 1])
            if isinstance(arr, list):
                for item in arr:
                    if not isinstance(item, dict):
                        continue
                    kid = str(item.get("id", "")).strip()
                    val = item.get("text")
                    if kid in id_map and isinstance(val, str) and val.strip():
                        got[id_map[kid]] = val
                if got:
                    return got
        except json.JSONDecodeError:
            pass

    for line in text.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        kid, val = line.split("=", 1)
        kid = kid.strip()
        if kid in id_map and val.strip():
            got[id_map[kid]] = val.strip()
    return got


def _replacement_looks_safe(original: str, new: str) -> bool:
    """拒绝明显被截断的译文（尤其是弄坏 ${}）。"""
    if original.count("${") != new.count("${"):
        return False
    # 译文不应比原文短太多且弄丢换行（旧 bug：多行被压成一行残片）
    if "\n" in original and "\n" not in new and len(new) < max(8, int(len(original) * 0.6)):
        return False
    if "${" in new:
        # 新串自身须能完整闭合插值
        try:
            bodies = _interpolation_bodies(new)
            if new.count("${") != len(bodies):
                return False
        except Exception:
            return False
    return True


def translate_script_strings_batch(strings: list[str], llm_cfg, log) -> dict[str, str]:
    """翻译去重后的字符串列表，返回 {原文: 译文}。"""
    unique = []
    seen = set()
    for s in strings:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    if not unique:
        return {}

    mapping: dict[str, str] = {}
    batch_size = 30
    for i in range(0, len(unique), batch_size):
        batch = unique[i : i + batch_size]
        payload = [{"id": f"S{n:04d}", "text": s} for n, s in enumerate(batch)]
        prompt = SCRIPT_TRANSLATE_PROMPT.replace(
            "__BATCH__", json.dumps(payload, ensure_ascii=False, indent=2)
        )
        try:
            out = translate_text(llm_cfg, prompt, log)
        except Exception:
            for s in batch:
                mapping[s] = s
            continue
        id_map = {f"S{n:04d}": s for n, s in enumerate(batch)}
        got = _parse_llm_json_batch(out, id_map)
        for s in batch:
            translated = got.get(s, s)
            if translated != s and not _replacement_looks_safe(s, translated):
                log(f"  ! 丢弃可疑译文（可能截断）: {s[:48]!r} → {translated[:48]!r}")
                mapping[s] = s
            else:
                mapping[s] = translated
        log(f"  脚本字符串批次 {i // batch_size + 1}: {len(batch)} 条")
    return mapping


def apply_replacements(source: str, spans: list[tuple[int, int, str]], mapping: dict[str, str]) -> tuple[str, int]:
    """按 span 从后往前替换，返回 (新文本, 实际替换数)。"""
    changed = 0
    result = source
    for start, end, original in sorted(spans, key=lambda x: x[0], reverse=True):
        new = mapping.get(original)
        if not new or new == original:
            continue
        if not _replacement_looks_safe(original, new):
            continue
        result = result[:start] + new + result[end:]
        changed += 1
    return result, changed


def _structural_check(source: str) -> tuple[bool, str]:
    """不依赖 Node 时的括号/引号粗检。"""
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch in "'\"`":
            parsed = _parse_string_literal(source, i)
            if not parsed:
                return False, f"未闭合字符串（{ch}）"
            _c, _c0, c1, _q = parsed
            i = c1 + 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            i = source.find("\n", i)
            if i < 0:
                break
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            j = source.find("*/", i + 2)
            if j < 0:
                return False, "未闭合块注释"
            i = j + 2
            continue
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return False, f"括号不匹配：意外的 {ch}"
            stack.pop()
        i += 1
    if stack:
        return False, f"括号未闭合：{''.join(stack)}"
    return True, ""


def _node_check(source: str, suffix: str) -> tuple[bool, str]:
    """用 node --check 校验 JS 语法。"""
    import subprocess
    import sys
    import tempfile

    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(source)
            path = tmp.name
        kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": 20,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(["node", "--check", path], **kwargs)
        if proc.returncode == 0:
            return True, ""
        err = (proc.stderr or proc.stdout or "syntax error").strip()
        lines = [ln.strip() for ln in err.splitlines() if ln.strip()]
        useful = [ln for ln in lines if "SyntaxError" in ln or "Error" in ln]
        if useful:
            return False, useful[0]
        if len(lines) >= 2:
            return False, " | ".join(lines[:3])
        return False, lines[0] if lines else "syntax error"
    except FileNotFoundError:
        return _structural_check(source)
    except Exception as e:
        ok, msg = _structural_check(source)
        if not ok:
            return False, msg
        return True, f"node 检查不可用（{e}），已用结构检查通过"
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


def validate_script_source(source: str, suffix: str) -> tuple[bool, str]:
    """校验脚本源码；JS 用 node，其它用结构检查。"""
    suf = (suffix or ".js").lower()
    if suf in {".js", ".mjs", ".cjs"}:
        return _node_check(source, suf)
    return _structural_check(source)


def localize_scripts_in(root: Path, llm_cfg, log) -> tuple[int, int, int, int]:
    """
    汉化目录下脚本提示字符串。
    返回 (扫描文件数, 待译字符串出现次数, 写入成功数, 校验失败回滚数)。
    """
    root = Path(root)
    files = list(iter_script_files(root))
    if not files:
        log("  无脚本文件")
        return 0, 0, 0, 0

    all_spans: list[tuple[Path, list[tuple[int, int, str]], str]] = []
    all_strings: list[str] = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            log(f"  跳过 {fp.name}: {e}")
            continue
        spans = extract_tip_strings(text)
        if not spans:
            continue
        all_spans.append((fp, spans, text))
        all_strings.extend(s for _, _, s in spans)

    total_hits = len(all_strings)
    log(f"  扫描 {len(files)} 个脚本，命中提示字符串 {total_hits} 处（去重 {len(set(all_strings))}）")
    if total_hits == 0:
        return len(files), 0, 0, 0

    mapping = translate_script_strings_batch(all_strings, llm_cfg, log)
    written = 0
    rolled_back = 0
    for fp, spans, text in all_spans:
        new_text, n = apply_replacements(text, spans, mapping)
        if n <= 0 or new_text == text:
            continue
        rel = fp.relative_to(root)
        old_ok, old_err = validate_script_source(text, fp.suffix)
        new_ok, new_err = validate_script_source(new_text, fp.suffix)
        if old_ok and not new_ok:
            rolled_back += 1
            log(f"  ✗ 汉化失败已回退: {rel}")
            log(f"    原因: {new_err}")
            continue
        if not old_ok and not new_ok:
            struct_ok, struct_err = _structural_check(new_text)
            if not struct_ok:
                rolled_back += 1
                log(f"  ✗ 汉化失败已回退: {rel}")
                log(f"    原因: {struct_err}")
                continue
            log(f"  ! {rel}: 原文未通过严格语法检查（{old_err}），已用结构检查放行")
        try:
            fp.write_text(new_text, encoding="utf-8")
            written += 1
            log(f"  ✓ 已写入 {rel}（{n} 处，语法检查通过）")
        except OSError as e:
            log(f"  写入失败 {fp.name}: {e}")
    if rolled_back:
        log(f"  共 {rolled_back} 个文件汉化后格式异常，已保持原文未改")
    return len(files), total_hits, written, rolled_back
