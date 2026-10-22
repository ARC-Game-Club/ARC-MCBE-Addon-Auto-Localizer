# -*- coding: utf-8 -*-
"""pack_manage_service：开发目录移动 / 删除 / 配置清理 单测。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from utils.pack_manage_service import (
    delete_pack_dirs,
    move_mod_packs_to_development,
    move_pack_to_development,
    plan_dev_move,
    prune_config_selection,
)


class FakeConfig:
    def __init__(self, **initial):
        self.data = {
            "resource_pack_path": "",
            "behavior_pack_path": "",
            "current_mod_name": "",
        }
        self.data.update(initial)
        self.saved = 0

    def get(self, *keys):
        d = self.data
        for k in keys:
            d = d[k]
        return d

    def set(self, value, *keys):
        d = self.data
        for k in keys[:-1]:
            d = d[k]
        d[keys[-1]] = value

    def save(self):
        self.saved += 1


class PlanDevMoveTests(unittest.TestCase):
    def test_official_dirs_map_to_development(self):
        base = Path("C:/mc/com.mojang")
        self.assertEqual(
            plan_dev_move(base / "resource_packs" / "Foo RP"),
            base / "development_resource_packs",
        )
        self.assertEqual(
            plan_dev_move(base / "behavior_packs" / "Foo BP"),
            base / "development_behavior_packs",
        )

    def test_non_official_returns_none(self):
        base = Path("C:/mc/com.mojang")
        self.assertIsNone(plan_dev_move(base / "development_resource_packs" / "Foo"))
        self.assertIsNone(plan_dev_move(base / "development_behavior_packs" / "Foo"))
        self.assertIsNone(plan_dev_move(Path("C:/elsewhere/mods/Foo")))


class MovePackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "com.mojang"
        self.addCleanup(self._tmp.cleanup)

    def _make_pack(self, official: str, name: str) -> Path:
        pack = self.base / official / name
        (pack / "texts").mkdir(parents=True)
        (pack / "manifest.json").write_text("{}", encoding="utf-8")
        return pack

    def test_move_official_pack_to_development(self):
        pack = self._make_pack("resource_packs", "Demo RP")
        dest, err = move_pack_to_development(pack)
        self.assertEqual(err, "")
        self.assertIsNotNone(dest)
        self.assertEqual(dest.parent, self.base / "development_resource_packs")
        self.assertEqual(dest.name, "Demo RP")
        self.assertTrue((dest / "manifest.json").is_file())
        self.assertFalse(pack.exists())

    def test_move_pack_in_development_is_noop(self):
        pack = self._make_pack("development_behavior_packs", "Demo BP")
        dest, err = move_pack_to_development(pack)
        self.assertIsNone(dest)
        self.assertEqual(err, "")
        self.assertTrue(pack.exists())

    def test_move_with_name_conflict_gets_suffix(self):
        pack = self._make_pack("behavior_packs", "Demo BP")
        existing = self.base / "development_behavior_packs" / "Demo BP"
        existing.mkdir(parents=True)
        existing.joinpath("keep.txt").write_text("x", encoding="utf-8")
        dest, err = move_pack_to_development(pack)
        self.assertEqual(err, "")
        self.assertEqual(dest.name, "Demo BP_2")
        self.assertTrue((dest / "manifest.json").is_file())
        self.assertTrue((existing / "keep.txt").is_file())


class MoveModPacksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "com.mojang"
        self.addCleanup(self._tmp.cleanup)
        self.logs: list[str] = []

    def _make_pack(self, official: str, name: str) -> Path:
        pack = self.base / official / name
        pack.mkdir(parents=True)
        (pack / "manifest.json").write_text("{}", encoding="utf-8")
        return pack

    def test_moves_both_packs_and_updates_config(self):
        rp = self._make_pack("resource_packs", "Demo RP")
        bp = self._make_pack("behavior_packs", "Demo BP")
        cfg = FakeConfig()
        moved, new_rp, new_bp = move_mod_packs_to_development(
            rp, bp, cfg, self.logs.append
        )
        self.assertTrue(moved)
        self.assertEqual(Path(new_rp).parent.name, "development_resource_packs")
        self.assertEqual(Path(new_bp).parent.name, "development_behavior_packs")
        self.assertEqual(cfg.get("resource_pack_path"), new_rp)
        self.assertEqual(cfg.get("behavior_pack_path"), new_bp)
        self.assertGreaterEqual(cfg.saved, 1)
        self.assertFalse(rp.exists())
        self.assertFalse(bp.exists())

    def test_no_move_when_already_development(self):
        rp = self._make_pack("development_resource_packs", "Demo RP")
        cfg = FakeConfig(resource_pack_path=str(rp))
        moved, new_rp, _ = move_mod_packs_to_development(
            rp, None, cfg, self.logs.append
        )
        self.assertFalse(moved)
        self.assertEqual(new_rp, str(rp))
        self.assertEqual(cfg.saved, 0)


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_delete_pack_dirs(self):
        p1 = self.base / "a"
        p2 = self.base / "b"
        for p in (p1, p2):
            p.mkdir()
            (p / "f.txt").write_text("x", encoding="utf-8")
        ok, errors = delete_pack_dirs([p1, p2, self.base / "missing"])
        self.assertEqual((ok, errors), (2, []))
        self.assertFalse(p1.exists())
        self.assertFalse(p2.exists())

    def test_prune_config_selection_clears_deleted_paths(self):
        rp = self.base / "resource_packs" / "Demo RP"
        other = self.base / "resource_packs" / "Keep RP"
        cfg = FakeConfig(
            resource_pack_path=str(rp),
            behavior_pack_path=str(other),
            current_mod_name="Demo",
        )
        hit = prune_config_selection(cfg, [rp])
        self.assertTrue(hit)
        self.assertEqual(cfg.get("resource_pack_path"), "")
        self.assertEqual(cfg.get("behavior_pack_path"), str(other))
        self.assertEqual(cfg.get("current_mod_name"), "")
        self.assertGreaterEqual(cfg.saved, 1)

    def test_prune_config_selection_untouched(self):
        rp = self.base / "resource_packs" / "Demo RP"
        cfg = FakeConfig(resource_pack_path=str(rp), current_mod_name="Demo")
        hit = prune_config_selection(cfg, [self.base / "resource_packs" / "Other RP"])
        self.assertFalse(hit)
        self.assertEqual(cfg.get("resource_pack_path"), str(rp))
        self.assertEqual(cfg.saved, 0)


if __name__ == "__main__":
    unittest.main()
