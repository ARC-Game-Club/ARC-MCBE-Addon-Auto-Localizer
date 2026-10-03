# -*- coding: utf-8 -*-
"""display_name_service.derive_lang_key / namespace 收集 单测。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json

from utils.display_name_service import (
    collect_pack_namespaces,
    derive_lang_key,
    standardize_display_names_for_mod,
)
from utils.lang_files import read_lang_map


class DeriveLangKeyTests(unittest.TestCase):
    def test_spawn_egg_entity_uses_egg_key_and_actual_namespace(self):
        data = {
            "format_version": "1.20.0",
            "minecraft:entity": {
                "description": {
                    "identifier": "apple:illager_war_banner",
                    "spawn_egg": {"base_color": "#fff", "overlay_color": "#000"},
                },
                "components": {
                    # 故意放另一 namespace 引用，旧逻辑若递归会串前缀
                    "minecraft:loot": {"table": "loot_tables/strawberries/dummy.json"},
                },
            },
        }
        key = derive_lang_key(data, "entity/banners/illager_war_banner.json")
        self.assertEqual(
            key, "item.spawn_egg.entity.apple:illager_war_banner.name"
        )

    def test_client_entity_without_spawn_egg(self):
        data = {
            "minecraft:client_entity": {
                "description": {"identifier": "apple:shillager"},
            }
        }
        key = derive_lang_key(data, "entity/shillager/shillager.json")
        self.assertEqual(key, "entity.apple:shillager.name")

    def test_bp_entity_without_spawn_egg(self):
        data = {
            "minecraft:entity": {
                "description": {"identifier": "strawberries:rifle_ammo_drone"},
            }
        }
        self.assertEqual(
            derive_lang_key(data, "entities/rifle_ammo_drone.json"),
            "entity.strawberries:rifle_ammo_drone.name",
        )

    def test_block_by_component(self):
        data = {
            "minecraft:block": {
                "description": {"identifier": "apple:banner_block"},
            }
        }
        self.assertEqual(
            derive_lang_key(data, "blocks/banner_block.json"),
            "tile.apple:banner_block.name",
        )

    def test_block_by_path_even_without_guessing_wrong_ns(self):
        data = {
            "minecraft:block": {
                "description": {"identifier": "apple:stone_pad"},
            }
        }
        # 即使路径像 entity，组件是 block 仍走 tile + 实际 ns
        self.assertEqual(
            derive_lang_key(data, "blocks/stone_pad.json"),
            "tile.apple:stone_pad.name",
        )

    def test_item_by_component(self):
        data = {
            "minecraft:item": {
                "description": {"identifier": "strawberries:rifle_ammo"},
            }
        }
        self.assertEqual(
            derive_lang_key(data, "items/rifle_ammo.json"),
            "item.strawberries:rifle_ammo.name",
        )

    def test_entity_path_is_not_treated_as_tile(self):
        data = {
            "minecraft:entity": {
                "description": {
                    "identifier": "apple:illager_war_banner",
                    "spawn_egg": {},
                },
            }
        }
        key = derive_lang_key(data, "entity/banners/illager_war_banner.json")
        self.assertFalse(key.startswith("tile."))
        self.assertTrue(key.startswith("item.spawn_egg.entity.apple:"))


class CollectNamespacesTests(unittest.TestCase):
    def test_collects_dual_namespaces_and_survives_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "entities" / "a").mkdir(parents=True)
            (root / "entities" / "b").mkdir(parents=True)
            (root / "items").mkdir()
            (root / "entities" / "a" / "good.json").write_text(
                '{"minecraft:entity":{"description":{"identifier":"apple:a","spawn_egg":{}}}}',
                encoding="utf-8",
            )
            (root / "entities" / "b" / "broken.json").write_text(
                "{not valid json!!!",
                encoding="utf-8",
            )
            (root / "items" / "ammo.json").write_text(
                '{"minecraft:item":{"description":{"identifier":"strawberries:rifle_ammo"}}}',
                encoding="utf-8",
            )
            logs: list[str] = []
            ns = collect_pack_namespaces(root, log=logs.append)
            self.assertEqual(ns, {"apple", "strawberries"})
            self.assertTrue(any("解析失败" in m for m in logs))


def _item_json(identifier: str, display: str) -> str:
    return json.dumps(
        {
            "format_version": "1.20.0",
            "minecraft:item": {
                "description": {"identifier": identifier},
                "components": {"minecraft:display_name": {"value": display}},
            },
        },
        ensure_ascii=False,
    )


class MirrorLangToResourcePackTests(unittest.TestCase):
    def test_bp_display_name_keys_are_written_to_rp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bp = root / "behavior_packs" / "Mod BP"
            rp = root / "resource_packs" / "Mod RP"
            (bp / "items").mkdir(parents=True)
            rp.mkdir(parents=True)
            (bp / "items" / "potion.json").write_text(
                _item_json("arc:potion", "Health Potion"),
                encoding="utf-8",
            )
            logs: list[str] = []
            standardize_display_names_for_mod(
                [("资源包", rp), ("行为包", bp)],
                "zh_CN",
                logs.append,
            )
            written = json.loads(
                (bp / "items" / "potion.json").read_text(encoding="utf-8")
            )
            value = written["minecraft:item"]["components"]["minecraft:display_name"][
                "value"
            ]
            self.assertEqual(value, "item.arc:potion.name")
            for pack in (bp, rp):
                en = read_lang_map(pack / "texts" / "en_US.lang")
                zh = read_lang_map(pack / "texts" / "zh_CN.lang")
                self.assertEqual(en.get("item.arc:potion.name"), "Health Potion")
                self.assertEqual(zh.get("item.arc:potion.name"), "Health Potion")
            self.assertTrue(any("同步语言键到资源包" in m for m in logs))

    def test_existing_rp_entry_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bp = root / "Mod BP"
            rp = root / "Mod RP"
            (bp / "items").mkdir(parents=True)
            (rp / "texts").mkdir(parents=True)
            (bp / "items" / "potion.json").write_text(
                _item_json("arc:potion", "item.arc:potion.name"),
                encoding="utf-8",
            )
            (bp / "texts").mkdir()
            (bp / "texts" / "en_US.lang").write_text(
                "item.arc:potion.name=Health Potion\n",
                encoding="utf-8",
            )
            (bp / "texts" / "languages.json").write_text(
                '["en_US"]\n', encoding="utf-8"
            )
            (rp / "texts" / "en_US.lang").write_text(
                "item.arc:potion.name=Existing English\n",
                encoding="utf-8",
            )
            (rp / "texts" / "zh_CN.lang").write_text(
                "item.arc:potion.name=已有译文\n",
                encoding="utf-8",
            )
            (rp / "texts" / "languages.json").write_text(
                '["en_US", "zh_CN"]\n', encoding="utf-8"
            )
            standardize_display_names_for_mod(
                [("资源包", rp), ("行为包", bp)],
                "zh_CN",
                lambda _m: None,
            )
            rp_en = read_lang_map(rp / "texts" / "en_US.lang")
            rp_zh = read_lang_map(rp / "texts" / "zh_CN.lang")
            self.assertEqual(rp_en["item.arc:potion.name"], "Existing English")
            self.assertEqual(rp_zh["item.arc:potion.name"], "已有译文")

    def test_bp_only_does_not_require_rp(self):
        with tempfile.TemporaryDirectory() as tmp:
            bp = Path(tmp) / "behavior_packs" / "Mod BP"
            (bp / "items").mkdir(parents=True)
            (bp / "items" / "potion.json").write_text(
                _item_json("arc:potion", "Health Potion"),
                encoding="utf-8",
            )
            standardize_display_names_for_mod(
                [("行为包", bp)],
                "zh_CN",
                lambda _m: None,
            )
            en = read_lang_map(bp / "texts" / "en_US.lang")
            self.assertEqual(en.get("item.arc:potion.name"), "Health Potion")


if __name__ == "__main__":
    unittest.main()
