#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JavaScript 格式化脚本
用于重新格式化混淆过的 JavaScript 文件

约束（避免汉化后 Bedrock 脚本挂掉）：
- 不在包内留下旁路 *.backup（MC 会当资源加载）
- 格式化后必须通过「普通字符串禁真换行」+ 语法检查，否则回滚不写盘
- 若格式化把依赖 ASI 的多语句压到同一行，拒绝写盘
"""

import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import jsbeautifier
except ImportError:
    print("正在安装 jsbeautifier...")
    os.system(f"{sys.executable} -m pip install jsbeautifier")
    import jsbeautifier

SKIP = "skip"

# `)\s+ident` / `}\s+ident` 且中间无分号：ASI 在同行不触发
_ASI_JOIN_RE = re.compile(
    r"[}\)][ \t]+(?=[A-Za-z_$]|return\b|throw\b|break\b|continue\b|debugger\b)"
)


def _atomic_write(path: str, content: str) -> None:
    path = str(path)
    directory = str(Path(path).parent)
    fd, tmp = tempfile.mkstemp(prefix=".fmt_", suffix=".js", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _asi_risk_increased(original: str, formatted: str) -> bool:
    """格式化后新增多语句同行粘连（无分号），视为危险。"""
    def risky_sites(text: str) -> set[str]:
        sites = set()
        for m in _ASI_JOIN_RE.finditer(text):
            # 用前后各 12 字符作指纹，忽略空白差异
            a = max(0, m.start() - 12)
            b = min(len(text), m.end() + 12)
            frag = re.sub(r"\s+", " ", text[a:b])
            sites.add(frag)
        return sites

    return len(risky_sites(formatted) - risky_sites(original)) > 0


def format_js_file(input_path, output_path=None, quiet=True, log=None):
    """
    格式化 JavaScript 文件。

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径，如果为None则覆盖原文件
        quiet: True 时不刷屏打印（批量规范化默认）
        log: 可选回调；出错时优先写入日志（便于 UI 显示）
    """
    def _p(msg):
        if not quiet:
            print(msg)

    def _err(msg):
        if log:
            log(msg)
        else:
            print(msg)

    def _skip(msg):
        if log:
            log(msg)

    name = Path(input_path).name
    if name.endswith(".backup") or name.endswith(".bak"):
        _skip(f"  跳过: {name}（备份文件）")
        return SKIP

    _p(f"正在读取文件: {input_path}")

    try:
        with open(input_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except UnicodeDecodeError:
        _skip(
            f"  跳过: {name}（非 UTF-8 文本，可能是 marketplace 缓存/二进制文件）"
        )
        return SKIP
    except OSError as e:
        _err(f"读取失败: {input_path} ({e})")
        return False

    _p(f"文件大小: {len(content)} 字符")
    _p("正在格式化...")

    opts = jsbeautifier.default_options()
    opts.indent_size = 4
    opts.indent_char = " "
    opts.preserve_newlines = True
    opts.max_preserve_newlines = 2
    opts.keep_array_indentation = False
    opts.break_chained_methods = False
    opts.indent_scripts = "normal"
    opts.brace_style = "collapse"
    opts.space_before_conditional = True
    opts.unescape_strings = False
    opts.wrap_line_length = 0
    opts.end_with_newline = True

    try:
        formatted = jsbeautifier.beautify(content, opts)
    except Exception as e:
        _err(f"JS 格式化失败: {input_path} ({e})")
        return False

    # 内容无变化：不写盘
    if formatted == content:
        _p("内容已是规范格式，跳过")
        return True

    # 安全校验：绝不能写出 Bedrock 会挂的脚本
    try:
        from utils.script_localize_service import validate_script_source
    except Exception:
        from script_localize_service import validate_script_source  # type: ignore

    new_ok, new_err = validate_script_source(formatted, Path(input_path).suffix or ".js")
    if not new_ok:
        _err(f"  跳过写盘（格式化后语法不安全）: {name} — {new_err}")
        return SKIP

    if _asi_risk_increased(content, formatted):
        _err(
            f"  跳过写盘（格式化可能把多语句压到一行且无分号，破坏 ASI）: {name}"
        )
        return SKIP

    if output_path is None:
        output_path = input_path

    _p(f"正在写入文件: {output_path}")
    try:
        _atomic_write(output_path, formatted)
    except Exception as e:
        _err(f"写入失败: {output_path} ({e})")
        return False

    _p("格式化完成！")
    _p(f"原始大小: {len(content)} 字符")
    _p(f"格式化后大小: {len(formatted)} 字符")

    return True


def main():
    """主函数"""
    default_input = r"C:\Users\DEVILENMO\AppData\Roaming\Minecraft Bedrock\Users\Shared\games\com.mojang\behavior_packs\RL Craft B\scripts\main.js"

    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        input_path = default_input

    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    else:
        output_path = None

    if not os.path.exists(input_path):
        print(f"错误: 文件不存在: {input_path}")
        sys.exit(1)

    success = format_js_file(input_path, output_path, quiet=False)

    if success:
        print("\n格式化成功完成！")
        sys.exit(0)
    else:
        print("\n格式化失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
