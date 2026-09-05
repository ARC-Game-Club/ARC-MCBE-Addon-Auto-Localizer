# -*- coding: utf-8 -*-
"""行为包脚本提示字符串本地化。

针对 sendMessage / form.title|button|label|body|toggle|… / setActionBar|setTitle|setSubtitle
以及 dropdown 选项数组、tooltip/placeholderText、tellraw rawtext.text、
以及 UPDATES_CHANGELOG 类 UI 常量数组中的字符串字面量，调用 LLM 只改提示文字，
保留 § 颜色码、占位符与 ${} 插值。语言键引用（无空格的 a.b.c）与复杂多行模板跳过。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .llm_service import translate_text
from .text_utils import needs_translation

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

# tellraw / titleraw JSON 里的可见 text 字段（常包在 runCommand 模板字符串中）
RAWTEXT_TEXT_RE = re.compile(r'"text"\s*:', re.M)

# const UPDATES_CHANGELOG = [ "..." ] 一类展示用常量数组
UI_CONST_ARRAY_RE = re.compile(
    r"\bconst\s+([A-Z][A-Z0-9_]*)\s*=\s*\[",
    re.M,
)
UI_CONST_NAME_HINT_RE = re.compile(
    r"(CHANGELOG|TITLES?|MESSAGES?|TIPS?|HELP|DESCS?|LABELS?|TEXTS?|NEWS|HINTS?|ALERTS?|NOTIFY)",
    re.I,
)

# 疑似语言文件键：foo.bar / pack.ui.toggle_x（无空格、无 §）
_LANG_KEY_RE = re.compile(r"^[A-Za-z][\w]*(\.[\w]+)+$")

# 资源路径（误伤过 Remove/Despawn 这种 UI 文案，故收紧）
_RESOURCE_PATH_RE = re.compile(
    r"^(?:textures|texture|sounds|models|particles|fonts|ui|entities|blocks?)/"
    r"|/\S+\.(?:png|jpg|jpeg|tga|fsb|ogg|wav|mp3|json|lang)$",
    re.I,
)

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

SCRIPT_TRANSLATE_PROMPT = """你是 Minecraft 基岩版模组脚本本地化专家。
下面是从 JS/TS 脚本中提取的玩家可见提示字符串（JSON 数组），请译为{lang_label}。

规则：
1. 只翻译人类可读文字；不要改动代码结构
2. 完整保留 § 及后续格式/颜色码（如 §c、§l、§r）、\\n、\\t
3. 完整保留 ${...} 模板插值、%s、%1$s、{{...}} 等占位符，位置与内容都不要改
4. 已是{lang_label}或纯符号的保持原样
5. 译文必须是单行 JSON 字符串值：需要换行时只写 \\n 转义，禁止在译文里直接断行
6. 只返回 JSON 数组，每项格式 {"id":"S0000","text":"译文"}，id 与输入一致，不要其它说明

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
    "@minecraft/",
    "./",
    "../",
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
    """
    允许安全插值表达式：
    - cityInfo.name / items[0]
    - Math.floor(pred.distance) / foo.bar(a, 10)
    仍拒绝 .map/.join/箭头函数/嵌套模板/三元等。
    """
    b = body.strip()
    if not b:
        return False
    for m in _COMPLEX_CODE_MARKERS:
        if m in b:
            return False
    if any(tok in b for tok in ("{", "`", "?", ":", ";", "=")):
        return False
    # 标识符 / 属性链 / 数字下标
    member = r"[A-Za-z_$][\w.$]*(?:\[\d+\])?"
    if re.fullmatch(member, b):
        return True
    # 单层函数/方法调用：Math.floor(pred.distance)、parseInt(x, 10)
    arg = rf"(?:{member}|\d+)"
    call = rf"{member}\(\s*(?:{arg}(?:\s*,\s*{arg})*)?\s*\)"
    if re.fullmatch(call, b):
        return True
    return False


def _looks_like_lang_key(s: str) -> bool:
    """无空格的 a.b.c 形态，多半是 translate 键而非直接展示文案。"""
    t = s.strip()
    if " " in t or "\t" in t or "§" in t or "${" in t:
        return False
    return bool(_LANG_KEY_RE.fullmatch(t))


def _looks_like_resource_path(s: str) -> bool:
    """textures/...、*.png 等资源路径；不含 Remove/Despawn 这类 UI 文案。"""
    t = s.strip()
    if not t or " " in t or "§" in t or "${" in t:
        return False
    low = t.lower()
    for p in _SKIP_PREFIXES:
        if low.startswith(p):
            return True
    if _RESOURCE_PATH_RE.search(t):
        return True
    # 纯小写路径段 a/b/c（无大写单词）
    if "/" in t and re.fullmatch(r"[a-z0-9_./\-]+", t):
        return True
    return False


def _strip_line_continuations(content: str) -> str:
    """去掉 JS 字符串里的 LineContinuation（\\ + 换行），得到更接近字面值的文本。"""
    out: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        if content[i] == "\\" and i + 1 < n and content[i + 1] in "\r\n":
            i += 1
            if content[i] == "\r" and i + 1 < n and content[i + 1] == "\n":
                i += 2
            else:
                i += 1
            continue
        out.append(content[i])
        i += 1
    return "".join(out)


def _should_translate(s: str, target_code: str | None = None) -> bool:
    s = s.strip()
    if len(s) < 2:
        return False
    low = s.lower()
    for p in _SKIP_PREFIXES:
        if low.startswith(p):
            return False
    if _looks_like_resource_path(s):
        return False
    if _looks_like_lang_key(s):
        return False
    if not needs_translation(s, target_code):
        return False
    return True


def _is_safe_tip_string(s: str, target_code: str | None = None) -> bool:
    """
    可安全送去翻译的提示串。
    嵌套反引号、或 ${} 内含 map/join/箭头函数等代码表达式 → 跳过。
    真换行允许：写回时由 _fit_replacement_to_quote 收成 \\n。
    """
    # 先按去掉 LineContinuation 后的逻辑文本判断
    logical = _strip_line_continuations(s)
    if not _should_translate(logical, target_code):
        return False
    # 内容里再出现反引号 = 模板套模板
    if "`" in logical:
        return False
    if "${" in logical:
        for body in _interpolation_bodies(logical):
            if not _is_simple_interpolation_body(body):
                return False
        if not _interpolation_bodies(logical):
            return False
    return True


def _skip_trivia(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
            continue
        if text[i] == "/" and i + 1 < n:
            if text[i + 1] == "/":
                i = _skip_line_comment(text, i + 2)
                continue
            if text[i + 1] == "*":
                i = _skip_block_comment(text, i + 2)
                continue
        break
    return i


def _extract_call_tip_strings(
    text: str, after_open_paren: int
) -> list[tuple[int, int, str, str]]:
    """
    从一次提示 API 调用的实参里提取玩家可见字符串：
    - 顶层字符串实参（label / title / body）
    - 顶层数组里的字符串（dropdown 的 options）
    对象字面量内的字段交给 TIP_PROP_RE，避免误伤 defaultValue 等。
    返回 (内容起始, 内容结束, 原文内容, 引号类型)。
    """
    hits: list[tuple[int, int, str, str]] = []
    i = after_open_paren
    n = len(text)
    paren = 1
    bracket = 0
    brace = 0
    while i < n and paren > 0:
        i = _skip_trivia(text, i)
        if i >= n:
            break
        ch = text[i]
        if ch in "'\"`":
            parsed = _parse_string_literal(text, i)
            if not parsed:
                break
            content, c0, c1, quote = parsed
            if brace == 0 and paren == 1 and bracket <= 1:
                hits.append((c0, c1, content, quote))
            i = c1 + 1
            continue
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        i += 1
    return hits


def extract_tip_strings(
    source: str, target_code: str | None = None
) -> list[tuple[int, int, str, str]]:
    """
    提取脚本中提示调用的字符串实参（含 dropdown 选项数组），以及 tooltip 等选项字段、
    tellraw rawtext.text、UI 常量数组元素。
    返回 [(内容起始, 内容结束, 原文内容, 引号), ...]，按出现顺序；同位置不重复。
    """
    hits: list[tuple[int, int, str, str]] = []
    seen_spans: set[tuple[int, int]] = set()

    def add(c0: int, c1: int, content: str, quote: str) -> None:
        key = (c0, c1)
        if key in seen_spans:
            return
        if not _is_safe_tip_string(content, target_code):
            return
        seen_spans.add(key)
        hits.append((c0, c1, content, quote))

    for m in TIP_METHOD_RE.finditer(source):
        for c0, c1, content, quote in _extract_call_tip_strings(source, m.end()):
            add(c0, c1, content, quote)

    for m in TIP_PROP_RE.finditer(source):
        parsed = _parse_string_literal(source, m.end())
        if not parsed:
            continue
        content, c0, c1, quote = parsed
        add(c0, c1, content, quote)

    # tellraw / title rawtext: "text": "玩家可见"
    for m in RAWTEXT_TEXT_RE.finditer(source):
        parsed = _parse_string_literal(source, m.end())
        if not parsed:
            continue
        content, c0, c1, quote = parsed
        add(c0, c1, content, quote)

    # const UPDATES_CHANGELOG = [ "...", ... ]
    for m in UI_CONST_ARRAY_RE.finditer(source):
        name = m.group(1)
        if not UI_CONST_NAME_HINT_RE.search(name):
            continue
        for c0, c1, content, quote in _extract_array_string_elements(source, m.end()):
            add(c0, c1, content, quote)

    hits.sort(key=lambda x: x[0])
    return hits


def _extract_array_string_elements(
    text: str, after_open_bracket: int
) -> list[tuple[int, int, str, str]]:
    """从 `[` 之后提取顶层字符串元素，直到匹配的 `]`。"""
    hits: list[tuple[int, int, str, str]] = []
    i = after_open_bracket
    n = len(text)
    bracket = 1
    brace = 0
    paren = 0
    while i < n and bracket > 0:
        i = _skip_trivia(text, i)
        if i >= n:
            break
        ch = text[i]
        if ch in "'\"`":
            parsed = _parse_string_literal(text, i)
            if not parsed:
                break
            content, c0, c1, quote = parsed
            if bracket == 1 and brace == 0 and paren == 0:
                hits.append((c0, c1, content, quote))
            i = c1 + 1
            continue
        if ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        i += 1
    return hits


def _fit_replacement_to_quote(text: str, quote: str) -> str:
    """
    把译文写回「引号内源码内容」，且不改变引号类型。

    普通 ' / \" 字符串（ES）：禁止出现未转义的 LineTerminator。
    - 译文里的真换行/回车 → 写成 \\n / \\r
    - 已有的 \\n 两字符转义保持不动（不二次转义）
    - 裸引号补 \\

    模板字符串：允许真换行；只转义反引号，避免提前结束字面量。
    """
    if quote == "`":
        out: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(text[i + 1])
                i += 2
                continue
            if ch == "`":
                out.append("\\`")
            else:
                out.append(ch)
            i += 1
        return "".join(out)

    if quote not in ("'", '"'):
        return text

    # 先把非法的真 LineTerminator / Tab 收成转义；不动已有 \\n 文本
    text = (
        text.replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(text[i + 1])
            i += 2
            continue
        if ch == "\\":
            out.append("\\\\")
            i += 1
            continue
        if ch == quote:
            out.append("\\" + quote)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


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


def translate_script_strings_batch(
    strings: list[str], llm_cfg, log, lang_label: str = "简体中文"
) -> dict[str, str]:
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
    template = SCRIPT_TRANSLATE_PROMPT.replace("{lang_label}", lang_label)
    for i in range(0, len(unique), batch_size):
        batch = unique[i : i + batch_size]
        payload = [{"id": f"S{n:04d}", "text": s} for n, s in enumerate(batch)]
        prompt = template.replace(
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


def apply_replacements(
    source: str,
    spans: list[tuple[int, int, str, str]],
    mapping: dict[str, str],
) -> tuple[str, int]:
    """按 span 从后往前替换，返回 (新文本, 实际替换数)。

    替换时按原引号类型编码译文：普通字符串绝不为了排版引入真换行。
    mapping 的键为「去掉 LineContinuation 后的逻辑原文」。
    """
    changed = 0
    result = source
    for start, end, original, quote in sorted(spans, key=lambda x: x[0], reverse=True):
        logical = _strip_line_continuations(original)
        new = mapping.get(logical)
        if new is None:
            new = mapping.get(original)
        if not new or new == logical:
            continue
        if not _replacement_looks_safe(logical, new):
            continue
        fitted = _fit_replacement_to_quote(new, quote)
        if fitted == original:
            continue
        result = result[:start] + fitted + result[end:]
        changed += 1
    return result, changed


def _illegal_string_newlines(source: str) -> tuple[bool, str]:
    """
    ES StringLiteral 不得含未转义 LineTerminator；模板字符串可以。
    V8/node --check 会把 \\r 当普通字符漏检，这里按规范补上。
    """
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "/" and i + 1 < n:
            nxt = source[i + 1]
            if nxt == "/":
                i = _skip_line_comment(source, i + 2)
                continue
            if nxt == "*":
                i = _skip_block_comment(source, i + 2)
                continue
        if ch not in "'\"`":
            i += 1
            continue
        quote = ch
        i += 1
        while i < n:
            c = source[i]
            if quote in ("'", '"') and c in "\r\n":
                return False, f"普通字符串字面量含真换行（引号 {quote}）"
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if quote == "`" and c == "$" and i + 1 < n and source[i + 1] == "{":
                i = _skip_template_interpolation(source, i + 1)
                continue
            if c == quote:
                i += 1
                break
            i += 1
        else:
            return False, f"未闭合字符串（{quote}）"
    return True, ""


def _structural_check(source: str) -> tuple[bool, str]:
    """不依赖 Node 时的括号/引号粗检 + 普通字符串禁真换行。"""
    ok, err = _illegal_string_newlines(source)
    if not ok:
        return False, err
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
            _c, c0, c1, quote = parsed
            if quote in ("'", '"') and (
                "\n" in source[c0:c1] or "\r" in source[c0:c1]
            ):
                return False, f"普通字符串字面量含真换行（引号 {quote}）"
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
    """校验脚本源码；先做 ES 字符串换行检查（补 node 漏检），再 node/结构检查。"""
    ok, err = _illegal_string_newlines(source)
    if not ok:
        return False, err
    suf = (suffix or ".js").lower()
    if suf in {".js", ".mjs", ".cjs"}:
        return _node_check(source, suf)
    return _structural_check(source)


def localize_scripts_in(
    root: Path,
    llm_cfg,
    log,
    lang_label: str = "简体中文",
    target_code: str | None = None,
) -> tuple[int, int, int, int]:
    """
    本地化目录下脚本提示字符串。
    返回 (扫描文件数, 待译字符串出现次数, 写入成功数, 校验失败回滚数)。
    """
    root = Path(root)
    files = list(iter_script_files(root))
    if not files:
        log("  无脚本文件")
        return 0, 0, 0, 0

    all_spans: list[tuple[Path, list[tuple[int, int, str, str]], str]] = []
    all_strings: list[str] = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            log(f"  跳过 {fp.name}: {e}")
            continue
        spans = extract_tip_strings(text, target_code)
        if not spans:
            continue
        all_spans.append((fp, spans, text))
        all_strings.extend(_strip_line_continuations(s) for _, _, s, _q in spans)

    total_hits = len(all_strings)
    log(f"  扫描 {len(files)} 个脚本，命中提示字符串 {total_hits} 处（去重 {len(set(all_strings))}）")
    if total_hits == 0:
        return len(files), 0, 0, 0

    mapping = translate_script_strings_batch(
        all_strings, llm_cfg, log, lang_label=lang_label
    )
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
            log(f"  ✗ 本地化失败已回退: {rel}")
            log(f"    原因: {new_err}")
            continue
        if not old_ok and not new_ok:
            struct_ok, struct_err = _structural_check(new_text)
            if not struct_ok:
                rolled_back += 1
                log(f"  ✗ 本地化失败已回退: {rel}")
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
        log(f"  共 {rolled_back} 个文件本地化后格式异常，已保持原文未改")
    return len(files), total_hits, written, rolled_back
