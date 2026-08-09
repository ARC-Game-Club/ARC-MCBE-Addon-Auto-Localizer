#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JavaScript 格式化脚本
用于重新格式化混淆过的 JavaScript 文件
"""

import os
import sys

try:
    import jsbeautifier
except ImportError:
    print("正在安装 jsbeautifier...")
    os.system(f"{sys.executable} -m pip install jsbeautifier")
    import jsbeautifier


def format_js_file(input_path, output_path=None, quiet=True):
    """
    格式化 JavaScript 文件。

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径，如果为None则覆盖原文件
        quiet: True 时不刷屏打印（批量规范化默认）
    """
    def _p(msg):
        if not quiet:
            print(msg)

    _p(f"正在读取文件: {input_path}")

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        _p(f"读取文件失败: {e}")
        return False

    _p(f"文件大小: {len(content)} 字符")
    _p("正在格式化...")

    opts = jsbeautifier.default_options()
    opts.indent_size = 4
    opts.indent_char = ' '
    opts.preserve_newlines = True
    opts.max_preserve_newlines = 2
    opts.keep_array_indentation = False
    opts.break_chained_methods = False
    opts.indent_scripts = 'normal'
    opts.brace_style = 'collapse'
    opts.space_before_conditional = True
    opts.unescape_strings = False
    opts.wrap_line_length = 0
    opts.end_with_newline = True

    try:
        formatted = jsbeautifier.beautify(content, opts)
    except Exception as e:
        _p(f"格式化失败: {e}")
        return False

    # 内容无变化：不写盘、不建 backup
    if formatted == content:
        _p("内容已是规范格式，跳过")
        return True

    if output_path is None:
        backup_path = input_path + '.backup'
        _p(f"创建备份: {backup_path}")
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            _p(f"创建备份失败: {e}")
            return False
        output_path = input_path

    _p(f"正在写入文件: {output_path}")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(formatted)
    except Exception as e:
        _p(f"写入文件失败: {e}")
        return False

    _p("格式化完成！")
    _p(f"原始大小: {len(content)} 字符")
    _p(f"格式化后大小: {len(formatted)} 字符")

    return True


def main():
    """主函数"""
    # 默认输入文件路径
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
    
    success = format_js_file(input_path, output_path)
    
    if success:
        print("\n格式化成功完成！")
        sys.exit(0)
    else:
        print("\n格式化失败！")
        sys.exit(1)


if __name__ == '__main__':
    main()