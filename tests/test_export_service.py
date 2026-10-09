# -*- coding: utf-8 -*-
"""导出文件名的版本号：模组名里的 x.x.x 优先，否则用行为包版本。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from utils.export_service import (
    build_export_filename,
    export_localized_pack,
    version_in_mod_name,
    version_to_append,
)


def _pack(root: Path, name: str, version) -> Path:
    pack = root / name
    pack.mkdir()
    (pack / "manifest.json").write_text(
        json.dumps({"header": {"name": name, "version": version}}),
        encoding="utf-8",
    )
    return pack


class ExportVersionTests(unittest.TestCase):
    def test_appends_behavior_pack_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bp = _pack(root, "BP", [1, 4, 2])
            rp = _pack(root, "RP", [9, 9, 9])
            version, src = version_to_append("Cool Mod", bp, rp)
            self.assertEqual((version, src), ("1.4.2", "bp"))
            name = build_export_filename("Cool Mod", "DEVILENMO", True, "zh_CN", version)
            self.assertTrue(name.startswith("Cool Mod 1.4.2"))
            self.assertTrue(name.endswith(".mcaddon"))
            self.assertNotIn("9.9.9", name)

    def test_mod_name_version_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            bp = _pack(Path(tmp), "BP", [9, 0, 0])
            version, src = version_to_append("Cool Mod v2.0.1", bp, None)
            self.assertEqual((version, src), (None, "name"))
            self.assertEqual(version_in_mod_name("Cool Mod v2.0.1"), "2.0.1")
            name = build_export_filename(
                "Cool Mod v2.0.1", "DEVILENMO", True, "zh_CN", version
            )
            self.assertIn("v2.0.1", name)
            self.assertNotIn("9.0.0", name)

    def test_falls_back_to_resource_pack_when_no_behavior_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            rp = _pack(Path(tmp), "RP", [3, 1, 0])
            version, src = version_to_append("Solo", None, rp)
            self.assertEqual((version, src), ("3.1.0", "rp"))

    def test_export_filename_uses_behavior_pack_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bp = _pack(root, "BP", [1, 2, 3])
            rp = _pack(root, "RP", [0, 0, 1])
            out = root / "out"
            logs: list[str] = []
            dest = export_localized_pack(
                out, "Cool Mod", "DEVILENMO", rp, bp, logs.append, "zh_CN"
            )
            self.assertTrue(dest.name.startswith("Cool Mod 1.2.3"))
            self.assertTrue(dest.name.endswith(".mcaddon"))
            self.assertTrue(any("1.2.3（行为包）" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
