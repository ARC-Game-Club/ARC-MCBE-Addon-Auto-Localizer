# -*- coding: utf-8 -*-
"""ocr_image_service 文字/底色采样与自动对比色 单测。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from utils import ocr_image_service as svc
from utils.ocr_image_service import (
    RegionRecord,
    _box_bounds,
    _build_plan,
    _color_dist,
    _contrast_ratio,
    _paint_backgrounds,
    _pick_text_color,
    _sample_background_color,
    _sample_text_color,
    _write_translations,
)

_NOOP_LOG = lambda *_: None  # noqa: E731

BOX = np.array([[10.0, 8.0], [150.0, 8.0], [150.0, 32.0], [10.0, 32.0]])


class PickTextColorTests(unittest.TestCase):
    def test_keeps_original_when_contrast_sufficient(self):
        self.assertEqual(_pick_text_color((20, 20, 60), (240, 240, 240)), (20, 20, 60))

    def test_darkens_to_target_on_light_bg(self):
        bg = (120, 120, 120)
        out = _pick_text_color((88, 88, 88), bg)
        self.assertGreaterEqual(_contrast_ratio(out, bg), svc.TARGET_CONTRAST_RATIO)
        self.assertEqual(out[0], out[1], out[2])

    def test_lightens_to_target_on_dark_bg(self):
        bg = (40, 40, 40)
        out = _pick_text_color((30, 30, 30), bg)
        self.assertGreaterEqual(_contrast_ratio(out, bg), svc.TARGET_CONTRAST_RATIO)
        self.assertGreater(out[0], 30)

    def test_gray_on_gray_pushes_to_target_contrast(self):
        bg = (128, 128, 128)
        out = _pick_text_color((110, 110, 110), bg)
        self.assertGreaterEqual(_contrast_ratio(out, bg), svc.TARGET_CONTRAST_RATIO)

    def test_prefers_design_direction_endpoint_over_flip(self):
        # 浅字灰底：提亮端点（纯白）可达 3:1 以上，不应翻转成黑字
        self.assertEqual(_pick_text_color((200, 200, 200), (128, 128, 128)), (255, 255, 255))


class SampleTextColorTests(unittest.TestCase):
    def test_light_text_on_dark_bg(self):
        arr = np.zeros((40, 160, 3), dtype=np.uint8)
        arr[:, :] = (20, 20, 60)
        arr[14:26, 30:120] = (245, 245, 245)  # 深底上的浅色“文字”块
        text = _sample_text_color(arr, BOX, bg_ref=(20, 20, 60))
        self.assertLess(_color_dist(text, (245, 245, 245)), 30)

    def test_dark_text_on_light_bg(self):
        arr = np.zeros((40, 160, 3), dtype=np.uint8)
        arr[:, :] = (235, 235, 235)
        arr[14:26, 30:120] = (30, 30, 30)
        text = _sample_text_color(arr, BOX, bg_ref=(235, 235, 235))
        self.assertLess(_color_dist(text, (30, 30, 30)), 30)

    def test_background_sampling_excludes_text(self):
        arr = np.zeros((40, 160, 3), dtype=np.uint8)
        arr[:, :] = (20, 20, 60)
        arr[14:26, 30:120] = (245, 245, 245)
        text = _sample_text_color(arr, BOX, bg_ref=(20, 20, 60))
        bg = _sample_background_color(arr, BOX, svc.PAD_PX, text)
        self.assertLess(_color_dist(bg, (20, 20, 60)), 45)


class PaintWriteContrastTests(unittest.TestCase):
    def test_low_contrast_text_gets_auto_color(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ui.png"
            img = Image.new("RGB", (160, 40), (117, 117, 117))
            img.paste((90, 90, 90), (30, 14, 120, 26))  # 灰底上的灰“文字”块
            img.save(path)

            region = RegionRecord(box=BOX.copy(), text="Hello", score=0.9)
            with patch.object(svc, "_run_ocr", return_value=[region]):
                plan = _build_plan(path, _NOOP_LOG)
            self.assertIsNotNone(plan)
            region = plan.regions[0]
            # 灰底灰字：原字色与采样底色对比不足
            self.assertLess(
                _contrast_ratio(region.text_color, region.bg_color),
                svc.MIN_CONTRAST_RATIO,
            )
            self.assertTrue(_paint_backgrounds(plan, _NOOP_LOG))
            self.assertTrue(_write_translations(plan, _NOOP_LOG))

            out = np.array(Image.open(path).convert("RGB"))
            x0, y0, x1, y1 = _box_bounds(region.box)
            box_px = out[y0:y1, x0:x1].reshape(-1, 3)
            # 涂底矩形内、文字框外的点，核对涂底颜色（LSB 水印可能 ±1）
            fill_px = tuple(int(v) for v in out[y0 - 2, x0 - 2])
            self.assertLessEqual(
                max(abs(a - b) for a, b in zip(fill_px, region.bg_color)), 2
            )
            darkest = tuple(int(v) for v in box_px[box_px.sum(axis=1).argmin()])
            self.assertGreaterEqual(_contrast_ratio(darkest, fill_px), svc.MIN_CONTRAST_RATIO)

    def test_sufficient_contrast_keeps_sampled_color(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ui.png"
            img = Image.new("RGB", (160, 40), (245, 245, 245))
            img.paste((30, 30, 30), (30, 14, 120, 26))  # 白底上的黑“文字”块
            img.save(path)

            region = RegionRecord(box=BOX.copy(), text="Hello", score=0.9)
            with patch.object(svc, "_run_ocr", return_value=[region]):
                plan = _build_plan(path, _NOOP_LOG)
            self.assertIsNotNone(plan)
            region = plan.regions[0]
            self.assertGreaterEqual(
                _contrast_ratio(region.text_color, region.bg_color),
                svc.MIN_CONTRAST_RATIO,
            )
            self.assertTrue(_paint_backgrounds(plan, _NOOP_LOG))
            self.assertTrue(_write_translations(plan, _NOOP_LOG))

            out = np.array(Image.open(path).convert("RGB"))
            x0, y0, x1, y1 = _box_bounds(region.box)
            box_px = out[y0:y1, x0:x1].reshape(-1, 3)
            darkest = tuple(int(v) for v in box_px[box_px.sum(axis=1).argmin()])
            self.assertLess(_color_dist(darkest, region.text_color), 30)


if __name__ == "__main__":
    unittest.main()
