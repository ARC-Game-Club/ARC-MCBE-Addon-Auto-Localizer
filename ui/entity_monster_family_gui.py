# -*- coding: utf-8 -*-
"""
实体 monster 家族标签工具 GUI
扫描世界行为包下所有实体，检测 minecraft:behavior.nearest_attackable_target：
若目标包含 player 或无明显条件（攻击所有生物），则在该实体的 minecraft:type_family.family 中加入 monster，
以便铁傀儡等会主动攻击该生物。
另：可导出带 monster 家族的实体按血量一半计算的击杀奖励列表（identifier=数字）到 txt。
"""
import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path


def find_behavior_packs(world_dir):
    """在世界目录或 behavior_packs 目录下查找所有行为包路径。"""
    world_path = Path(world_dir)
    bp_dir = world_path / "behavior_packs" if (world_path / "behavior_packs").is_dir() else world_path
    if not bp_dir.is_dir():
        return []
    return [p for p in bp_dir.iterdir() if p.is_dir()]


def find_entity_files(pack_path):
    """在行为包目录下递归查找 entities 文件夹内所有 .json 文件（含多级子目录）。"""
    entities_dir = pack_path / "entities"
    if not entities_dir.is_dir():
        return []
    return list(entities_dir.rglob("*.json"))


def _filters_contain_player(filters):
    """递归检查 filter 树中是否包含 is_family == 'player'。"""
    if not isinstance(filters, dict):
        return False
    if filters.get("test") == "is_family" and filters.get("value") == "player":
        return True
    for key in ("any_of", "all_of"):
        if key in filters and isinstance(filters[key], list):
            for item in filters[key]:
                if _filters_contain_player(item):
                    return True
    return False


def _filters_absent_or_empty(entity_type_entry):
    """entity_types 中某一项是否没有 filters 或 filters 为空，视为“无限制/攻击所有”。"""
    filters = entity_type_entry.get("filters") if isinstance(entity_type_entry, dict) else None
    if filters is None:
        return True
    if isinstance(filters, dict) and not filters:
        return True
    if isinstance(filters, list) and not filters:
        return True
    return False


def entity_types_target_player_or_all(entity_types):
    """
    若 entity_types 为空/缺失，或任一项目标为 player，或任一项无 filters，则返回 True。
    """
    if not entity_types or not isinstance(entity_types, list):
        return True
    for entry in entity_types:
        if not isinstance(entry, dict):
            continue
        if _filters_absent_or_empty(entry):
            return True
        filters = entry.get("filters")
        if _filters_contain_player(filters):
            return True
    return False


def get_attack_target_behaviors(components):
    """从组件字典中收集 nearest_attackable_target 及同类索敌行为（仅取配置）。"""
    out = []
    for key, val in (components or {}).items():
        if not isinstance(val, dict):
            continue
        if "nearest_attackable_target" in key or "nearest_prioritized_attackable_target" in key:
            out.append(val)
    return out


def _component_set_has_tamed_guard(components):
    """该组件集合是否同时包含 is_tamed、owner_hurt_by_target、owner_hurt_target（驯服且会护主）。"""
    if not components or not isinstance(components, dict):
        return False
    has_tamed = "minecraft:is_tamed" in components
    has_owner_hurt_by = any("owner_hurt_by_target" in k for k in components if isinstance(k, str))
    has_owner_hurt = any("owner_hurt_target" in k for k in components if isinstance(k, str))
    return has_tamed and has_owner_hurt_by and has_owner_hurt


def entity_needs_monster_family(file_path, data):
    """
    判断该实体是否需要在 type_family 中加入 monster。
    若任意组件或组件组中存在索敌行为且目标包含 player 或无限制，则需要。
    """
    ent = data.get("minecraft:entity")
    if not ent or not isinstance(ent, dict):
        return False

    components_root = ent.get("components") or {}
    component_groups = ent.get("component_groups") or {}

    all_component_sets = [components_root]
    for group_name, group_comps in component_groups.items():
        if isinstance(group_comps, dict):
            all_component_sets.append(group_comps)

    for comp_set in all_component_sets:
        for behavior in get_attack_target_behaviors(comp_set):
            entity_types = behavior.get("entity_types")
            if entity_types_target_player_or_all(entity_types):
                return True
    return False


def entity_needs_player_family(data):
    """
    判断该实体是否需要在 type_family 中加入 player。
    若任意组件或组件组中同时存在 is_tamed、owner_hurt_by_target、owner_hurt_target（驯服且会护主），则需要。
    """
    ent = data.get("minecraft:entity")
    if not ent or not isinstance(ent, dict):
        return False

    components_root = ent.get("components") or {}
    component_groups = ent.get("component_groups") or {}

    all_component_sets = [components_root]
    for group_name, group_comps in component_groups.items():
        if isinstance(group_comps, dict):
            all_component_sets.append(group_comps)

    for comp_set in all_component_sets:
        if _component_set_has_tamed_guard(comp_set):
            return True
    return False


def get_identifier_and_families(data):
    """返回 (identifier, family_list)。family_list 来自根 components 的 type_family。"""
    ent = data.get("minecraft:entity")
    if not ent:
        return None, []
    desc = ent.get("description") or {}
    identifier = desc.get("identifier", "")
    comps = ent.get("components") or {}
    type_family = comps.get("minecraft:type_family")
    if not isinstance(type_family, dict):
        return identifier, []
    family = type_family.get("family")
    if isinstance(family, list):
        return identifier, list(family)
    return identifier, []


def _family_list_from_type_family(type_family):
    if not isinstance(type_family, dict):
        return []
    family = type_family.get("family")
    if isinstance(family, list):
        return family
    return []


def entity_has_monster_family_anywhere(data):
    """根 components 或任意 component_group 的 type_family 中含 monster 即视为带 monster 的怪物。"""
    ent = data.get("minecraft:entity")
    if not ent or not isinstance(ent, dict):
        return False
    component_sets = [ent.get("components") or {}]
    for group_comps in (ent.get("component_groups") or {}).values():
        if isinstance(group_comps, dict):
            component_sets.append(group_comps)
    for comp_set in component_sets:
        tf = comp_set.get("minecraft:type_family")
        if "monster" in _family_list_from_type_family(tf):
            return True
    return False


def _health_from_component_set(components):
    """从单个组件集合读取 minecraft:health，优先 max，其次 value。"""
    if not isinstance(components, dict):
        return None
    health = components.get("minecraft:health")
    if not isinstance(health, dict):
        return None
    for key in ("max", "value"):
        if key in health:
            val = health[key]
            if isinstance(val, (int, float)):
                return int(val)
    return None


def get_entity_health_for_reward(data):
    """优先根 components，否则按顺序取第一个含 minecraft:health 的 component_group。"""
    ent = data.get("minecraft:entity")
    if not ent or not isinstance(ent, dict):
        return None
    root = ent.get("components") or {}
    hp = _health_from_component_set(root)
    if hp is not None:
        return hp
    for group_comps in (ent.get("component_groups") or {}).values():
        if isinstance(group_comps, dict):
            hp = _health_from_component_set(group_comps)
            if hp is not None:
                return hp
    return None


def scan_monster_kill_rewards(world_dir):
    """
    扫描所有带 monster 家族的实体，奖励 = 血量 // 2。
    返回 (entries, skipped_no_health, skipped_no_identifier)，entries 为 [(identifier, reward), ...]，
    同一 identifier 后出现的文件覆盖前者。
    """
    packs = find_behavior_packs(world_dir)
    by_identifier = {}
    skipped_no_health = 0
    skipped_no_identifier = 0

    for pack_path in packs:
        for file_path in find_entity_files(pack_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            if not entity_has_monster_family_anywhere(data):
                continue

            ent = data.get("minecraft:entity") or {}
            desc = ent.get("description") or {}
            identifier = (desc.get("identifier") or "").strip()
            if not identifier or ":" not in identifier:
                skipped_no_identifier += 1
                continue

            hp = get_entity_health_for_reward(data)
            if hp is None:
                skipped_no_health += 1
                continue

            reward = hp // 2
            by_identifier[identifier] = reward

    entries = sorted(by_identifier.items(), key=lambda x: x[0])
    return entries, skipped_no_health, skipped_no_identifier


def write_monster_kill_rewards_txt(out_path, entries):
    """写入每行 identifier=reward。"""
    lines = [f"{ident}={reward}\n" for ident, reward in entries]
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def scan_monster_tagged_identifiers(world_dir):
    """
    扫描所有在 type_family 中含 monster 的实体（根 components 或任意 component_group）。
    返回 (sorted_identifiers, skipped_no_identifier)。
    """
    packs = find_behavior_packs(world_dir)
    identifier_set = set()
    skipped_no_identifier = 0

    for pack_path in packs:
        for file_path in find_entity_files(pack_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            if not entity_has_monster_family_anywhere(data):
                continue

            ent = data.get("minecraft:entity") or {}
            desc = ent.get("description") or {}
            identifier = (desc.get("identifier") or "").strip()
            if not identifier or ":" not in identifier:
                skipped_no_identifier += 1
                continue

            identifier_set.add(identifier)

    return sorted(identifier_set), skipped_no_identifier


def write_monster_tag_list_txt(out_path, identifiers):
    """每行 "namespace:name", 便于粘贴到脚本/数组。"""
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for ident in identifiers:
            f.write(json.dumps(ident, ensure_ascii=False) + ",\n")


def add_monster_to_entity_file(file_path):
    """
    在该实体根 components 的 minecraft:type_family.family 中加入 "monster"（若尚未存在），并写回。
    返回 (success, message)。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, str(e)

    ent = data.get("minecraft:entity")
    if not ent:
        return False, "无 minecraft:entity"

    components = ent.get("components")
    if components is None:
        ent["components"] = {}
        components = ent["components"]

    type_family = components.get("minecraft:type_family")
    if type_family is None:
        type_family = {"family": []}
        components["minecraft:type_family"] = type_family
    if not isinstance(type_family.get("family"), list):
        type_family["family"] = []

    family_list = type_family["family"]
    if "monster" not in family_list:
        family_list.append("monster")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return False, str(e)
    return True, ""


def add_player_to_entity_file(file_path):
    """
    在该实体根 components 的 minecraft:type_family.family 中加入 "player"（若尚未存在），并写回。
    若没有 type_family 则先创建。返回 (success, message)。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, str(e)

    ent = data.get("minecraft:entity")
    if not ent:
        return False, "无 minecraft:entity"

    components = ent.get("components")
    if components is None:
        ent["components"] = {}
        components = ent["components"]

    type_family = components.get("minecraft:type_family")
    if type_family is None:
        type_family = {"family": []}
        components["minecraft:type_family"] = type_family
    if not isinstance(type_family.get("family"), list):
        type_family["family"] = []

    family_list = type_family["family"]
    if "player" not in family_list:
        family_list.append("player")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return False, str(e)
    return True, ""


def get_desired_entity_filename(identifier):
    """根据 identifier（如 spark:trader_scribe）得到目标文件名 trader_scribe.json。"""
    if not identifier or not isinstance(identifier, str):
        return None
    name = identifier.split(":")[-1].strip() if ":" in identifier else identifier.strip()
    if not name:
        return None
    return name + ".json"


def rename_entity_file_to_identifier(file_path, identifier):
    """
    将实体文件按 identifier 重命名为 name.json（同目录下）。
    返回 (success, message)。若当前已是目标名则跳过；若目标名已被其他文件占用则跳过。
    """
    desired_name = get_desired_entity_filename(identifier)
    if not desired_name:
        return False, "identifier 无效"
    path = Path(file_path)
    if not path.is_file():
        return False, "文件不存在"
    target_path = path.parent / desired_name
    if path.resolve() == target_path.resolve():
        return True, "(已是目标名)"
    if target_path.exists() and target_path.resolve() != path.resolve():
        return False, f"目标已存在: {target_path.name}"
    try:
        path.rename(target_path)
        return True, f"-> {desired_name}"
    except OSError as e:
        return False, str(e)


def scan_all_entities(world_dir):
    """
    扫描世界目录下所有行为包中的实体文件。
    返回 [(pack_name, pack_path, file_path, identifier, family_list, needs_monster), ...]
    """
    packs = find_behavior_packs(world_dir)
    results = []

    for pack_path in packs:
        pack_name = pack_path.name
        for file_path in find_entity_files(pack_path):
            path_str = str(file_path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            identifier, family_list = get_identifier_and_families(data)
            needs_monster = entity_needs_monster_family(path_str, data)
            has_monster = "monster" in family_list
            needs_player = entity_needs_player_family(data)
            has_player = "player" in family_list

            results.append({
                "pack_name": pack_name,
                "pack_path": str(pack_path),
                "file_path": path_str,
                "identifier": identifier or path_str,
                "family_list": family_list,
                "needs_monster": needs_monster,
                "has_monster": has_monster,
                "needs_player": needs_player,
                "has_player": has_player,
            })

    return results


class EntityMonsterFamilyApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("实体 monster 家族标签工具")
        self.root.geometry("900x500")
        self.root.minsize(700, 400)

        self.world_dir = tk.StringVar()
        self.scan_results = []

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding="8")
        top.pack(fill=tk.X)

        ttk.Label(top, text="世界目录（含 behavior_packs）:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(top, textvariable=self.world_dir, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(top, text="选择目录", command=self._on_select_dir).pack(side=tk.LEFT, padx=2)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        btn_frame = ttk.Frame(self.root, padding="8")
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="添加 monster 到需处理的实体", command=self._on_apply).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加 player 到驯服护卫实体", command=self._on_apply_player).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="按 identifier 重命名实体文件", command=self._on_rename_by_identifier).pack(side=tk.LEFT, padx=2)

        btn_frame2 = ttk.Frame(self.root, padding="8")
        btn_frame2.pack(fill=tk.X)
        ttk.Button(btn_frame2, text="导出带 monster 标签的实体列表", command=self._on_export_monster_tag_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame2, text="导出 monster 击杀奖励 txt（血量/2）", command=self._on_export_monster_kill_rewards).pack(side=tk.LEFT, padx=2)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        table_frame = ttk.Frame(self.root, padding="8")
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("mod", "identifier", "families", "needs_monster", "has_monster", "needs_player", "has_player")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=20, selectmode="browse")
        self.tree.heading("mod", text="模组")
        self.tree.heading("identifier", text="实体 identifier")
        self.tree.heading("families", text="当前 family")
        self.tree.heading("needs_monster", text="需加 monster")
        self.tree.heading("has_monster", text="已有 monster")
        self.tree.heading("needs_player", text="需加 player")
        self.tree.heading("has_player", text="已有 player")
        for col in columns:
            self.tree.column(col, width=90, stretch=True)
        self.tree.column("families", width=200)

        scroll_y = ttk.Scrollbar(table_frame)
        scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.configure(command=self.tree.yview)
        scroll_x.configure(command=self.tree.xview)

    def _on_select_dir(self):
        path = filedialog.askdirectory(title="选择世界文件夹（包含 behavior_packs 的目录）")
        if not path:
            return
        self.world_dir.set(path)
        self._refresh_scan()

    def _refresh_scan(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        world_dir = self.world_dir.get().strip()
        if not world_dir or not os.path.isdir(world_dir):
            return

        self.scan_results = scan_all_entities(world_dir)
        if not self.scan_results:
            messagebox.showinfo("提示", "未在该目录下找到任何行为包或实体文件。\n请确保选择的是包含 behavior_packs 的世界目录。")
            return

        for row in self.scan_results:
            families_str = ", ".join(row["family_list"]) if row["family_list"] else "(无)"
            self.tree.insert("", tk.END, values=(
                row["pack_name"],
                row["identifier"],
                families_str,
                "是" if row["needs_monster"] else "否",
                "是" if row["has_monster"] else "否",
                "是" if row["needs_player"] else "否",
                "是" if row["has_player"] else "否",
            ))

    def _on_apply(self):
        if not self.scan_results:
            messagebox.showwarning("警告", "请先选择世界目录并完成扫描。")
            return

        to_apply = [r for r in self.scan_results if r["needs_monster"] and not r["has_monster"]]
        if not to_apply:
            messagebox.showinfo("完成", "没有需要添加 monster 的实体（要么已包含 monster，要么不满足“目标玩家/无限制”条件）。")
            return

        ok_count = 0
        err_list = []
        for row in to_apply:
            success, msg = add_monster_to_entity_file(row["file_path"])
            if success:
                ok_count += 1
            else:
                err_list.append(f"{row['identifier']}: {msg}")

        if err_list:
            messagebox.showwarning(
                "部分失败",
                f"成功: {ok_count} 个文件。\n失败: {len(err_list)} 个。\n" + "\n".join(err_list[:5]) + ("\n..." if len(err_list) > 5 else "")
            )
        else:
            messagebox.showinfo("完成", f"已为 {ok_count} 个实体添加 monster 家族标签。\n请重新扫描以查看更新。")
        self._refresh_scan()

    def _on_apply_player(self):
        if not self.scan_results:
            messagebox.showwarning("警告", "请先选择世界目录并完成扫描。")
            return

        to_apply = [r for r in self.scan_results if r["needs_player"] and not r["has_player"]]
        if not to_apply:
            messagebox.showinfo("完成", "没有需要添加 player 的实体（要么已包含 player，要么不满足“驯服且护主”条件）。")
            return

        ok_count = 0
        err_list = []
        for row in to_apply:
            success, msg = add_player_to_entity_file(row["file_path"])
            if success:
                ok_count += 1
            else:
                err_list.append(f"{row['identifier']}: {msg}")

        if err_list:
            messagebox.showwarning(
                "部分失败",
                f"成功: {ok_count} 个文件。\n失败: {len(err_list)} 个。\n" + "\n".join(err_list[:5]) + ("\n..." if len(err_list) > 5 else "")
            )
        else:
            messagebox.showinfo("完成", f"已为 {ok_count} 个驯服护卫实体添加 player 家族标签。\n请重新扫描以查看更新。")
        self._refresh_scan()

    def _on_rename_by_identifier(self):
        if not self.scan_results:
            messagebox.showwarning("警告", "请先选择世界目录并完成扫描。")
            return
        ok_count = 0
        skip_same = 0
        err_list = []
        for row in self.scan_results:
            identifier = row["identifier"]
            if not identifier or ":" not in identifier:
                continue
            desired_name = get_desired_entity_filename(identifier)
            if not desired_name:
                continue
            current_name = Path(row["file_path"]).name
            if current_name == desired_name:
                skip_same += 1
                continue
            success, msg = rename_entity_file_to_identifier(row["file_path"], identifier)
            if success:
                ok_count += 1
            else:
                err_list.append(f"{identifier}: {msg}")
        parts = [f"已重命名: {ok_count} 个"]
        if skip_same:
            parts.append(f"已是目标名跳过: {skip_same} 个")
        if err_list:
            messagebox.showwarning(
                "按 identifier 重命名",
                "\n".join(parts) + f"\n失败: {len(err_list)} 个\n" + "\n".join(err_list[:8]) + ("\n..." if len(err_list) > 8 else "")
            )
        else:
            messagebox.showinfo("按 identifier 重命名", "\n".join(parts) + "。\n请重新扫描以查看更新。")
        self._refresh_scan()

    def _on_export_monster_kill_rewards(self):
        world_dir = self.world_dir.get().strip()
        if not world_dir or not os.path.isdir(world_dir):
            messagebox.showwarning("警告", "请先选择世界目录。")
            return
        out_path = filedialog.asksaveasfilename(
            title="保存击杀奖励列表",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="monster_kill_rewards.txt",
        )
        if not out_path:
            return
        entries, skipped_no_health, skipped_no_identifier = scan_monster_kill_rewards(world_dir)
        if not entries:
            messagebox.showinfo(
                "提示",
                "未生成任何条目：未找到同时带 monster 家族且含 minecraft:health 的实体。\n"
                f"（跳过无血量: {skipped_no_health}，跳过无 identifier: {skipped_no_identifier}）",
            )
            return
        try:
            write_monster_kill_rewards_txt(out_path, entries)
        except OSError as exc:
            messagebox.showerror("错误", f"写入失败: {exc}")
            return
        msg_parts = [f"已写入 {len(entries)} 条: {out_path}"]
        if skipped_no_health:
            msg_parts.append(f"跳过（无 minecraft:health）: {skipped_no_health} 个")
        if skipped_no_identifier:
            msg_parts.append(f"跳过（无有效 identifier）: {skipped_no_identifier} 个")
        messagebox.showinfo("完成", "\n".join(msg_parts))

    def _on_export_monster_tag_list(self):
        world_dir = self.world_dir.get().strip()
        if not world_dir or not os.path.isdir(world_dir):
            messagebox.showwarning("警告", "请先选择世界目录。")
            return
        out_path = filedialog.asksaveasfilename(
            title="保存带 monster 家族标签的实体列表",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="monster_tagged_entities.txt",
        )
        if not out_path:
            return
        identifiers, skipped_no_identifier = scan_monster_tagged_identifiers(world_dir)
        if not identifiers:
            msg = "未找到 type_family 中含 monster 的实体。"
            if skipped_no_identifier:
                msg += f"\n（另跳过无有效 identifier: {skipped_no_identifier} 个）"
            messagebox.showinfo("提示", msg)
            return
        try:
            write_monster_tag_list_txt(out_path, identifiers)
        except OSError as exc:
            messagebox.showerror("错误", f"写入失败: {exc}")
            return
        msg_parts = [f"已写入 {len(identifiers)} 个 identifier: {out_path}"]
        if skipped_no_identifier:
            msg_parts.append(f"跳过（无有效 identifier）: {skipped_no_identifier} 个")
        messagebox.showinfo("完成", "\n".join(msg_parts))

    def run(self):
        self.root.mainloop()


def main():
    app = EntityMonsterFamilyApp()
    app.run()


if __name__ == "__main__":
    main()
