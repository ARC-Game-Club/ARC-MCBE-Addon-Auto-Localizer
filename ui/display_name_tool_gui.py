#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Display Name 汉化工具 GUI
基于现有的提取和应用功能创建的图形界面工具
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path
import threading


def find_json_files(root: Path):
    """递归查找所有JSON文件"""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith('.json'):
                yield Path(dirpath) / name


def find_display_name_recursive(obj):
    """递归搜索整个JSON结构，找到minecraft:display_name字段"""
    if isinstance(obj, dict):
        # 如果当前字典中有 minecraft:display_name 键
        if 'minecraft:display_name' in obj:
            value = obj['minecraft:display_name']
            # 如果是字符串，直接返回
            if isinstance(value, str) and value:
                return value
            # 如果是字典，尝试获取 value 字段
            elif isinstance(value, dict) and 'value' in value:
                val = value['value']
                if isinstance(val, str) and val:
                    return val
        
        # 递归搜索所有值
        for v in obj.values():
            result = find_display_name_recursive(v)
            if result is not None:
                return result
    elif isinstance(obj, list):
        # 递归搜索列表中的每个元素
        for item in obj:
            result = find_display_name_recursive(item)
            if result is not None:
                return result
    
    return None


def load_mapping(mapping_path: Path):
    """加载映射文件"""
    mapping = {}
    for line in mapping_path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or '=' not in line:
            continue
        left, right = line.split('=', 1)
        # 右侧是JSON字符串字面量，解析以获取精确文本
        try:
            mapping[left] = json.loads(right)
        except json.JSONDecodeError:
            # 回退：作为原始字符串处理
            mapping[left] = right
    return mapping


def update_display_name_recursive(obj, new_value):
    """递归搜索并更新minecraft:display_name字段"""
    updated = False
    
    if isinstance(obj, dict):
        # 如果当前字典中有 minecraft:display_name 键
        if 'minecraft:display_name' in obj:
            old_value = obj['minecraft:display_name']
            # 如果是字符串，直接更新
            if isinstance(old_value, str):
                if old_value != new_value:
                    obj['minecraft:display_name'] = new_value
                    updated = True
            # 如果是字典，尝试更新 value 字段
            elif isinstance(old_value, dict) and 'value' in old_value:
                if old_value['value'] != new_value:
                    old_value['value'] = new_value
                    updated = True
            else:
                # 如果既不是字符串也不是字典，直接替换为字符串
                obj['minecraft:display_name'] = new_value
                updated = True
        
        # 递归搜索所有值
        for v in obj.values():
            if update_display_name_recursive(v, new_value):
                updated = True
    elif isinstance(obj, list):
        # 递归搜索列表中的每个元素
        for item in obj:
            if update_display_name_recursive(item, new_value):
                updated = True
    
    return updated


def get_behavior_packs_path():
    """获取 Minecraft Bedrock behavior_packs 目录路径"""
    user_profile = os.getenv('USERPROFILE') or os.path.expanduser('~')
    behavior_packs_path = Path(user_profile) / 'AppData' / 'Roaming' / 'Minecraft Bedrock' / 'Users' / 'Shared' / 'games' / 'com.mojang' / 'behavior_packs'
    return behavior_packs_path


def scan_mods():
    """扫描所有模组文件夹"""
    behavior_packs_path = get_behavior_packs_path()
    mods = []
    
    if not behavior_packs_path.exists():
        return mods
    
    try:
        for item in behavior_packs_path.iterdir():
            if item.is_dir():
                mods.append({
                    'name': item.name,
                    'path': str(item)
                })
    except Exception:
        pass
    
    return sorted(mods, key=lambda x: x['name'])


class DisplayNameToolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Display Name 汉化工具")
        self.root.geometry("900x700")
        
        # 变量
        self.folder_path = tk.StringVar()
        self.translation_file_path = tk.StringVar()
        self.output_file_path = tk.StringVar(value="display_names_translation.txt")
        self.mod_buttons = []  # 存储模组按钮
        
        # 创建界面
        self.create_widgets()
        
        # 自动扫描模组
        self.scan_and_display_mods()
        
    def create_widgets(self):
        # 主框架
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 快速选择模组区域
        mods_frame = tk.LabelFrame(main_frame, text="快速选择模组", padx=10, pady=10)
        mods_frame.pack(fill=tk.X, pady=5)
        
        # 刷新按钮和说明
        mods_header_frame = tk.Frame(mods_frame)
        mods_header_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(mods_header_frame, text="已找到的模组:", font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Button(mods_header_frame, text="刷新", command=self.scan_and_display_mods, 
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(10, 0))
        
        # 模组按钮容器（使用 Canvas 实现垂直滚动，支持多行显示）
        mods_canvas_frame = tk.Frame(mods_frame)
        mods_canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.mods_canvas = tk.Canvas(mods_canvas_frame, height=120)
        mods_scrollbar = tk.Scrollbar(mods_canvas_frame, orient="vertical", command=self.mods_canvas.yview)
        self.mods_canvas.configure(yscrollcommand=mods_scrollbar.set)
        
        self.mods_button_frame = tk.Frame(self.mods_canvas)
        self.mods_canvas_window = self.mods_canvas.create_window((0, 0), window=self.mods_button_frame, anchor="nw")
        
        mods_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.mods_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 绑定画布大小变化事件
        self.mods_button_frame.bind("<Configure>", self._on_mods_frame_configure)
        self.mods_canvas.bind("<Configure>", self._on_mods_canvas_configure)
        
        # 绑定鼠标滚轮事件
        def _on_mousewheel(event):
            self.mods_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.mods_canvas.bind("<MouseWheel>", _on_mousewheel)
        
        # 文件夹选择区域
        folder_frame = tk.LabelFrame(main_frame, text="1. 选择文件夹", padx=10, pady=10)
        folder_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(folder_frame, text="文件夹路径:").pack(anchor=tk.W)
        folder_entry_frame = tk.Frame(folder_frame)
        folder_entry_frame.pack(fill=tk.X, pady=5)
        tk.Entry(folder_entry_frame, textvariable=self.folder_path, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(folder_entry_frame, text="浏览...", command=self.select_folder).pack(side=tk.LEFT)
        
        # 提取功能区域
        extract_frame = tk.LabelFrame(main_frame, text="2. 提取 Display Name", padx=10, pady=10)
        extract_frame.pack(fill=tk.X, pady=5)
        
        output_file_frame = tk.Frame(extract_frame)
        output_file_frame.pack(fill=tk.X, pady=5)
        tk.Label(output_file_frame, text="输出文件:").pack(side=tk.LEFT, padx=(0, 5))
        tk.Entry(output_file_frame, textvariable=self.output_file_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(output_file_frame, text="选择...", command=self.select_output_file).pack(side=tk.LEFT)
        
        tk.Button(extract_frame, text="开始提取", command=self.extract_display_names, 
                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
        
        # 应用功能区域
        apply_frame = tk.LabelFrame(main_frame, text="3. 应用翻译", padx=10, pady=10)
        apply_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(apply_frame, text="翻译文件路径:").pack(anchor=tk.W)
        translation_file_frame = tk.Frame(apply_frame)
        translation_file_frame.pack(fill=tk.X, pady=5)
        tk.Entry(translation_file_frame, textvariable=self.translation_file_path, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        tk.Button(translation_file_frame, text="浏览...", command=self.select_translation_file).pack(side=tk.LEFT)
        
        tk.Button(apply_frame, text="应用翻译", command=self.apply_translations, 
                 bg="#2196F3", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
        
        # 日志区域
        log_frame = tk.LabelFrame(main_frame, text="日志", padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def _on_mods_frame_configure(self, event):
        """模组按钮框架大小变化时更新滚动区域"""
        self.mods_canvas.configure(scrollregion=self.mods_canvas.bbox("all"))
    
    def _on_mods_canvas_configure(self, event):
        """画布大小变化时调整内部框架宽度"""
        canvas_width = event.width
        self.mods_canvas.itemconfig(self.mods_canvas_window, width=canvas_width)
    
    def scan_and_display_mods(self):
        """扫描并显示所有模组"""
        # 清除现有按钮
        for button in self.mod_buttons:
            button.destroy()
        self.mod_buttons.clear()
        
        # 扫描模组
        mods = scan_mods()
        
        if not mods:
            behavior_packs_path = get_behavior_packs_path()
            no_mods_label = tk.Label(self.mods_button_frame, 
                                    text=f"未找到模组\n(检查路径: {behavior_packs_path})",
                                    fg="gray", font=("Arial", 8))
            no_mods_label.grid(row=0, column=0, padx=5, pady=5)
            self.mod_buttons.append(no_mods_label)
            self.log(f"未找到模组，路径: {behavior_packs_path}")
            return
        
        # 计算每行可以放几个按钮（根据按钮宽度和容器宽度）
        # 按钮宽度约150像素（包括padding），每行至少放4个
        buttons_per_row = 5
        
        # 使用grid布局创建模组按钮，自动换行
        for index, mod in enumerate(mods):
            row = index // buttons_per_row
            col = index % buttons_per_row
            
            mod_button = tk.Button(
                self.mods_button_frame,
                text=mod['name'],
                command=lambda path=mod['path'], name=mod['name']: self.select_mod(path, name),
                width=18,
                font=("Arial", 8),
                relief=tk.RAISED,
                bg="#E3F2FD"
            )
            mod_button.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
            self.mod_buttons.append(mod_button)
        
        # 配置列权重，让按钮均匀分布
        for col in range(buttons_per_row):
            self.mods_button_frame.columnconfigure(col, weight=1)
        
        self.log(f"找到 {len(mods)} 个模组")
        self.mods_canvas.configure(scrollregion=self.mods_canvas.bbox("all"))
    
    def select_mod(self, mod_path, mod_name):
        """选择模组"""
        self.folder_path.set(mod_path)
        self.log(f"已选择模组: {mod_name}")
        self.log(f"路径: {mod_path}")
    
    def log(self, message):
        """添加日志消息"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def select_folder(self):
        """选择文件夹"""
        folder = filedialog.askdirectory(title="选择包含JSON文件的文件夹")
        if folder:
            self.folder_path.set(folder)
            self.log(f"已选择文件夹: {folder}")
            
    def select_output_file(self):
        """选择输出文件"""
        file_path = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.output_file_path.set(file_path)
            self.log(f"已选择输出文件: {file_path}")
            
    def select_translation_file(self):
        """选择翻译文件"""
        file_path = filedialog.askopenfilename(
            title="选择翻译文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.translation_file_path.set(file_path)
            self.log(f"已选择翻译文件: {file_path}")
            
    def extract_display_names(self):
        """提取display_name字段"""
        folder = self.folder_path.get()
        if not folder:
            messagebox.showerror("错误", "请先选择文件夹！")
            return
            
        output_path = self.output_file_path.get()
        if not output_path:
            messagebox.showerror("错误", "请指定输出文件路径！")
            return
            
        # 在新线程中执行，避免界面冻结
        thread = threading.Thread(target=self._extract_worker, args=(folder, output_path))
        thread.daemon = True
        thread.start()
        
    def _extract_worker(self, folder, output_path):
        """提取工作线程"""
        try:
            self.log("\n" + "="*50)
            self.log("开始提取 Display Name...")
            
            root_path = Path(folder)
            if not root_path.exists():
                self.log(f"错误: 路径不存在: {root_path}")
                messagebox.showerror("错误", f"路径不存在: {root_path}")
                return
            
            if not root_path.is_dir():
                self.log(f"错误: 路径不是目录: {root_path}")
                messagebox.showerror("错误", f"路径不是目录: {root_path}")
                return

            out_path = Path(output_path)
            lines = []
            processed = 0
            found = 0

            self.log(f"正在扫描目录: {root_path}")
            for file_path in find_json_files(root_path):
                processed += 1
                try:
                    text = file_path.read_text(encoding='utf-8')
                    data = json.loads(text)
                except Exception as e:
                    continue

                value = find_display_name_recursive(data)
                if value is None:
                    continue

                found += 1
                rel_path = str(file_path.relative_to(root_path))
                # 使用JSON字符串字面量来保留转义字符和换行符
                right = json.dumps(value, ensure_ascii=False)
                lines.append(f"{rel_path}={right}")

            # 确保输出目录存在
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
            
            self.log(f"\n处理完成!")
            self.log(f"  扫描文件数: {processed}")
            self.log(f"  找到display_name: {found}")
            self.log(f"  输出文件: {out_path}")
            self.log("\n请手动编辑输出文件进行汉化，然后使用'应用翻译'功能应用回去")
            
            messagebox.showinfo("成功", f"提取完成！\n扫描文件数: {processed}\n找到display_name: {found}\n输出文件: {out_path}")
            
        except Exception as e:
            error_msg = f"提取过程中发生错误: {str(e)}"
            self.log(error_msg)
            messagebox.showerror("错误", error_msg)
            
    def apply_translations(self):
        """应用翻译"""
        folder = self.folder_path.get()
        if not folder:
            messagebox.showerror("错误", "请先选择文件夹！")
            return
            
        translation_file = self.translation_file_path.get()
        if not translation_file:
            messagebox.showerror("错误", "请先选择翻译文件！")
            return
            
        # 确认对话框
        if not messagebox.askyesno("确认", "确定要应用翻译吗？这将修改文件夹中的JSON文件。"):
            return
            
        # 在新线程中执行，避免界面冻结
        thread = threading.Thread(target=self._apply_worker, args=(folder, translation_file))
        thread.daemon = True
        thread.start()
        
    def _apply_worker(self, folder, translation_file):
        """应用工作线程"""
        try:
            self.log("\n" + "="*50)
            self.log("开始应用翻译...")
            
            root_path = Path(folder)
            if not root_path.exists():
                self.log(f"错误: 路径不存在: {root_path}")
                messagebox.showerror("错误", f"路径不存在: {root_path}")
                return
            
            if not root_path.is_dir():
                self.log(f"错误: 路径不是目录: {root_path}")
                messagebox.showerror("错误", f"路径不是目录: {root_path}")
                return

            mapping_path = Path(translation_file)
            if not mapping_path.exists():
                self.log(f"错误: 映射文件不存在: {mapping_path}")
                messagebox.showerror("错误", f"映射文件不存在: {mapping_path}")
                return

            mapping = load_mapping(mapping_path)
            self.log(f"加载了 {len(mapping)} 条映射记录")

            updated = 0
            skipped = 0
            not_found = 0

            for rel_path, new_value in mapping.items():
                file_path = root_path / rel_path
                if not file_path.exists():
                    not_found += 1
                    self.log(f"跳过: 文件不存在 - {rel_path}")
                    continue
                
                try:
                    text = file_path.read_text(encoding='utf-8')
                    data = json.loads(text)
                except Exception as e:
                    skipped += 1
                    self.log(f"跳过: 无法解析JSON - {rel_path}: {e}")
                    continue

                # 递归更新display_name
                if update_display_name_recursive(data, new_value):
                    # 格式化JSON并写回
                    new_text = json.dumps(data, ensure_ascii=False, indent=2)
                    if not new_text.endswith('\n'):
                        new_text += '\n'
                    file_path.write_text(new_text, encoding='utf-8')
                    updated += 1
                else:
                    skipped += 1

            self.log(f"\n处理完成!")
            self.log(f"  更新文件数: {updated}")
            self.log(f"  跳过文件数: {skipped}")
            self.log(f"  文件不存在: {not_found}")
            
            messagebox.showinfo("成功", f"应用完成！\n更新文件数: {updated}\n跳过文件数: {skipped}\n文件不存在: {not_found}")
            
        except Exception as e:
            error_msg = f"应用过程中发生错误: {str(e)}"
            self.log(error_msg)
            messagebox.showerror("错误", error_msg)


def main():
    root = tk.Tk()
    app = DisplayNameToolGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
