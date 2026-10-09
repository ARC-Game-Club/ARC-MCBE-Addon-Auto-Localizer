# -*- coding: utf-8 -*-
"""OCR 擦写图片本地化：RapidOCR 检测 → 擦除原文 → 文本 LLM 翻译 → PIL 写回。"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .llm_service import translate_image_texts

_OCR_ENGINE = None
_FONT_PATH: str | None = None

MIN_SCORE = 0.5
MIN_BOX_SIZE = 6
PAD_PX = 4
FALLBACK_ERASE = (255, 255, 255)
COLOR_BIN = 16
TEXT_COLOR_DIST = 45
MIN_CONTRAST_RATIO = 3.0
TARGET_CONTRAST_RATIO = 4.5


def _color_dist(c1: tuple[int, ...], c2: tuple[int, ...]) -> float:
    return float(np.sqrt(sum((int(a) - int(b)) ** 2 for a, b in zip(c1[:3], c2[:3]))))


def _is_similar(c1: tuple[int, ...], c2: tuple[int, ...], threshold: float = TEXT_COLOR_DIST) -> bool:
    return _color_dist(c1, c2) < threshold


def _rel_luminance(c: tuple[int, ...]) -> float:
    """WCAG 相对亮度。"""

    def lin(v: int) -> float:
        v = int(v) / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def _contrast_ratio(c1: tuple[int, ...], c2: tuple[int, ...]) -> float:
    l1, l2 = sorted((_rel_luminance(c1), _rel_luminance(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _scale_toward(
    c: tuple[int, int, int], target: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c, target))


def _pick_text_color(
    text_color: tuple[int, int, int],
    bg_color: tuple[int, int, int],
    min_ratio: float = MIN_CONTRAST_RATIO,
    target_ratio: float = TARGET_CONTRAST_RATIO,
) -> tuple[int, int, int]:
    """译文颜色：原字色与填充底色对比不足 3:1 时，沿原色相压暗/提亮到 4.5:1。

    首选方向（与原设计的深浅一致）到端点仍不足 3:1，才换反方向；黑/白都不达标则取对比最大的候选。
    """
    if _contrast_ratio(text_color, bg_color) >= min_ratio:
        return text_color
    darker = [_scale_toward(text_color, (0, 0, 0), k / 8) for k in range(1, 9)]
    lighter = [_scale_toward(text_color, (255, 255, 255), k / 8) for k in range(1, 9)]
    ramp = darker if _rel_luminance(text_color) <= _rel_luminance(bg_color) else lighter
    other = lighter if ramp is darker else darker
    for candidates in (ramp, other):
        for c in candidates:
            if _contrast_ratio(c, bg_color) >= target_ratio:
                return c
        # 端点即纯黑/纯白，是该方向对比最大的一档
        if _contrast_ratio(candidates[-1], bg_color) >= min_ratio:
            return candidates[-1]
    return max(darker + lighter, key=lambda c: _contrast_ratio(c, bg_color))


def _quantize_color(rgb) -> tuple[int, int, int]:
    step = COLOR_BIN
    return tuple(int(c) // step * step + step // 2 for c in rgb[:3])


def _dominant_color(pixels: np.ndarray, exclude: tuple[int, int, int] | None = None) -> tuple[int, int, int]:
    """取像素中出现次数最多的量化颜色，跳过与 exclude 相近的项。"""
    if len(pixels) == 0:
        return FALLBACK_ERASE

    from collections import Counter

    counter: Counter[tuple[int, int, int]] = Counter()
    for px in pixels:
        key = _quantize_color(px)
        counter[key] += 1

    for color, _count in counter.most_common():
        if exclude and _is_similar(color, exclude):
            continue
        return color

    # 环带/范围里全是字色：取次常见，或向亮度反方向偏移
    if counter:
        best = counter.most_common(1)[0][0]
        if exclude:
            er, eg, eb = exclude
            br, bg, bb = best
            lum_e = 0.299 * er + 0.587 * eg + 0.114 * eb
            lum_b = 0.299 * br + 0.587 * bg + 0.114 * bb
            if lum_e < lum_b:
                return (max(0, br - 40), max(0, bg - 40), max(0, bb - 40))
            return (min(255, br + 40), min(255, bg + 40), min(255, bb + 40))
        return best
    return FALLBACK_ERASE


def _collect_ring_pixels(arr: np.ndarray, box: np.ndarray, pad: int) -> np.ndarray:
    """文字框外一圈环带像素（尽量不含字）。"""
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = _box_bounds(box)
    ring = max(pad * 2, 6)
    ox0, oy0 = max(0, x0 - ring), max(0, y0 - ring)
    ox1, oy1 = min(w, x1 + ring), min(h, y1 + ring)

    strips: list[np.ndarray] = []
    if oy0 < y0:
        strips.append(arr[oy0:y0, ox0:ox1])
    if y1 < oy1:
        strips.append(arr[y1:oy1, ox0:ox1])
    if ox0 < x0:
        strips.append(arr[y0:y1, ox0:x0])
    if x1 < ox1:
        strips.append(arr[y0:y1, x1:ox1])

    if not strips:
        return np.empty((0, arr.shape[2]), dtype=arr.dtype)
    rows = [s.reshape(-1, arr.shape[2]) for s in strips if s.size > 0]
    if not rows:
        return np.empty((0, arr.shape[2]), dtype=arr.dtype)
    if len(rows) == 1:
        return rows[0]
    return np.vstack(rows)


def _collect_erase_region_pixels(arr: np.ndarray, box: np.ndarray, pad: int) -> np.ndarray:
    """待擦除矩形范围内的全部像素。"""
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = _box_bounds(box)
    ex0 = max(0, x0 - pad)
    ey0 = max(0, y0 - pad)
    ex1 = min(w, x1 + pad)
    ey1 = min(h, y1 + pad)
    return arr[ey0:ey1, ex0:ex1].reshape(-1, arr.shape[2])


def _filter_non_text_pixels(pixels: np.ndarray, text_color: tuple[int, int, int]) -> np.ndarray:
    if len(pixels) == 0:
        return pixels
    keep = [_quantize_color(px) for px in pixels]
    mask = np.array([not _is_similar(q, text_color) for q in keep])
    filtered = pixels[mask]
    return filtered if len(filtered) > 0 else pixels


@dataclass
class RegionRecord:
    box: np.ndarray
    text: str
    score: float
    text_color: tuple[int, int, int] = (0, 0, 0)
    bg_color: tuple[int, int, int] = FALLBACK_ERASE
    translation: str = ""


@dataclass
class ImagePlan:
    path: Path
    regions: list[RegionRecord]
    painted: bool = False


TEXT_BATCH_SIZE = 50


def _get_ocr_engine(log):
    """进程内单例 RapidOCR；未安装时返回 None。"""
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr import RapidOCR

        log("  初始化 RapidOCR 引擎（首次运行可能下载模型）…")
        _OCR_ENGINE = RapidOCR()
        return _OCR_ENGINE
    except ImportError:
        log("未安装 RapidOCR，请先执行: pip install rapidocr onnxruntime")
        return None
    except Exception as e:
        log(f"  RapidOCR 初始化失败: {e}")
        return None


def _find_font_path() -> str | None:
    """Windows 优先微软雅黑，否则黑体；其它平台尝试常见路径。"""
    global _FONT_PATH
    if _FONT_PATH is not None:
        return _FONT_PATH or None

    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for p in candidates:
        if p.is_file():
            _FONT_PATH = str(p)
            return _FONT_PATH
    _FONT_PATH = ""
    return None


def _box_bounds(box: np.ndarray) -> tuple[int, int, int, int]:
    xs = box[:, 0]
    ys = box[:, 1]
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _polygon_mask(h: int, w: int, box: np.ndarray) -> np.ndarray:
    from PIL import Image, ImageDraw

    mask_img = Image.new("L", (w, h), 0)
    poly = [tuple(p) for p in box]
    ImageDraw.Draw(mask_img).polygon(poly, fill=255)
    return np.array(mask_img) > 0


def _sample_background_color(
    arr: np.ndarray,
    box: np.ndarray,
    pad: int,
    text_color: tuple[int, int, int],
) -> tuple[int, int, int]:
    """擦除范围内出现最多的背景色，排除与文字色相近的像素。"""
    ring = _collect_ring_pixels(arr, box, pad)
    region = _collect_erase_region_pixels(arr, box, pad)

    # 优先用环带（纯背景）；不够则用擦除范围内非字色像素的众数
    if len(ring) >= 8:
        candidates = _filter_non_text_pixels(ring, text_color)
        if len(candidates) >= 4:
            return _dominant_color(candidates, exclude=text_color)

    if len(region) > 0:
        candidates = _filter_non_text_pixels(region, text_color)
        return _dominant_color(candidates, exclude=text_color)

    return FALLBACK_ERASE


def _sample_text_color(
    arr: np.ndarray,
    box: np.ndarray,
    bg_ref: tuple[int, int, int] | None = None,
) -> tuple[int, int, int]:
    """框内与底色差异最大的像素众数作为文字色；无底色参考时退回偏暗像素众数。"""
    h, w = arr.shape[:2]
    mask = _polygon_mask(h, w, box)
    pixels = arr[mask]
    if len(pixels) == 0:
        return (0, 0, 0)
    if pixels.shape[1] < 3:
        v = int(np.median(pixels))
        return (v, v, v)

    rgb = pixels[:, :3].astype(np.float32)
    if bg_ref is not None:
        dist = np.sqrt(((rgb - np.array(bg_ref[:3], np.float32)) ** 2).sum(axis=1))
        far = pixels[dist >= TEXT_COLOR_DIST]
        # 文字在框内占少数且与底色差距明显才可信，避免把底色/花纹当字色
        if len(far) >= max(4, int(len(pixels) * 0.03)):
            return _dominant_color(far)

    lum = 0.299 * rgb[:, 0] + 0.587 * rgb[:, 1] + 0.114 * rgb[:, 2]
    dark = pixels[lum <= np.percentile(lum, 55)]
    if len(dark) >= 4:
        return _dominant_color(dark)
    return _dominant_color(pixels)


def _erase_rect(draw, box: np.ndarray, pad: int, w: int, h: int, fill: tuple[int, int, int]) -> None:
    """用矩形覆盖文字区域。"""
    x0, y0, x1, y1 = _box_bounds(box)
    draw.rectangle(
        [max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)],
        fill=fill,
    )


def _load_font(font_path: str | None, size: int):
    from PIL import ImageFont

    size = max(6, size)
    try:
        if font_path:
            return ImageFont.truetype(font_path, size)
    except OSError:
        pass
    return ImageFont.load_default()


def _measure_text(draw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _font_for_box(
    draw,
    text: str,
    font_path: str | None,
    max_w: int,
    max_h: int,
) -> tuple:
    """字号优先匹配原框高度，仅在超出宽度时缩小。"""
    size = max(6, int(max_h * 0.92))
    font = _load_font(font_path, size)
    tw, th = _measure_text(draw, text, font)
    while size >= 6 and (tw > max_w or th > max_h):
        size -= 1
        font = _load_font(font_path, size)
        tw, th = _measure_text(draw, text, font)
    return font, tw, th


def _draw_translated_text(
    draw,
    box: np.ndarray,
    text: str,
    text_color: tuple[int, int, int],
    font_path: str | None,
) -> None:
    x0, y0, x1, y1 = _box_bounds(box)
    max_w = max(4, x1 - x0)
    max_h = max(4, y1 - y0)
    font, tw, th = _font_for_box(draw, text, font_path, max_w, max_h)
    tx = x0 + (max_w - tw) // 2
    ty = y0 + (max_h - th) // 2
    draw.text((tx, ty), text, fill=text_color, font=font)


def _sort_regions(regions: list[RegionRecord]) -> list[RegionRecord]:
    return sorted(regions, key=lambda r: (_box_bounds(r.box)[1], _box_bounds(r.box)[0]))


def _run_ocr(image_path: Path, log) -> list[RegionRecord]:
    engine = _get_ocr_engine(log)
    if engine is None:
        return []
    try:
        result = engine(str(image_path))
    except Exception as e:
        log(f"  OCR 识别失败: {e}")
        return []

    if result is None:
        log("  OCR 未识别到文字")
        return []

    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None) or ()
    scores = getattr(result, "scores", None) or ()

    if boxes is None or len(boxes) == 0:
        log("  OCR 未识别到文字")
        return []

    regions: list[RegionRecord] = []
    for i, box in enumerate(boxes):
        text = txts[i] if i < len(txts) else ""
        score = float(scores[i]) if i < len(scores) else 0.0
        text = (text or "").strip()
        if not text or score < MIN_SCORE:
            continue
        x0, y0, x1, y1 = _box_bounds(box)
        if (x1 - x0) < MIN_BOX_SIZE or (y1 - y0) < MIN_BOX_SIZE:
            continue
        regions.append(
            RegionRecord(box=np.array(box, dtype=float), text=text, score=score)
        )
    log(f"  OCR 识别 {len(regions)} 处文字")
    return regions


def _load_rgba(image_path: Path):
    from PIL import Image

    im = Image.open(image_path)
    im.load()
    orig_size = im.size
    orig_format = im.format or "PNG"
    rgba = im.convert("RGBA")
    im.close()
    return rgba, orig_format, orig_size


def _save_rgba(rgba, image_path: Path, orig_format: str, pnginfo=None) -> None:
    save_fmt = orig_format.upper()
    if save_fmt == "JPG":
        save_fmt = "JPEG"
    out = rgba
    if save_fmt == "JPEG" and out.mode == "RGBA":
        out = rgba.convert("RGB")
    save_kw = {"optimize": True} if save_fmt == "PNG" else {}
    if save_fmt == "PNG" and pnginfo is not None:
        save_kw["pnginfo"] = pnginfo
    out.save(image_path, format=save_fmt, **save_kw)


def _build_plan(image_path: Path, log) -> ImagePlan | None:
    """步骤 1：OCR 并记录位置、原文、文字色、底色（读原图采样）。"""
    regions = _sort_regions(_run_ocr(image_path, log))
    if not regions:
        return None
    try:
        rgba, _fmt, _size = _load_rgba(image_path)
    except Exception as e:
        log(f"  打开图片失败: {e}")
        return None
    arr = np.array(rgba)
    for region in regions:
        ring = _collect_ring_pixels(arr, region.box, PAD_PX)
        bg_ref = _dominant_color(ring) if len(ring) >= 8 else None
        region.text_color = _sample_text_color(arr, region.box, bg_ref)
        region.bg_color = _sample_background_color(
            arr, region.box, PAD_PX, region.text_color
        )
    return ImagePlan(path=image_path, regions=regions)


def _backup_image(image_path: Path, log) -> None:
    backup_dir = image_path.parent / "_backup"
    try:
        backup_dir.mkdir(exist_ok=True)
        shutil.copy2(str(image_path), str(backup_dir / image_path.name))
        log(f"  已备份原图到 {backup_dir.name}/")
    except OSError as e:
        log(f"  备份失败: {e}")


def _paint_backgrounds(plan: ImagePlan, log) -> bool:
    """步骤 2：粉刷全部底色。"""
    from PIL import ImageDraw

    try:
        rgba, orig_format, orig_size = _load_rgba(plan.path)
    except Exception as e:
        log(f"  打开图片失败: {e}")
        return False

    h, w = rgba.size[1], rgba.size[0]
    draw = ImageDraw.Draw(rgba)
    for region in plan.regions:
        _erase_rect(draw, region.box, PAD_PX, w, h, region.bg_color)

    if rgba.size != orig_size:
        log(f"  尺寸异常 {rgba.size} != {orig_size}")
        return False
    try:
        _save_rgba(rgba, plan.path, orig_format)
        return True
    except Exception as e:
        log(f"  保存图片失败: {e}")
        return False


def _write_translations(plan: ImagePlan, log) -> bool:
    """步骤 3b：写回全部译文并打水印。"""
    from PIL import ImageDraw

    from .watermark_service import png_text_chunk, stamp_image

    try:
        rgba, orig_format, orig_size = _load_rgba(plan.path)
    except Exception as e:
        log(f"  打开图片失败: {e}")
        return False

    draw = ImageDraw.Draw(rgba)
    font_path = _find_font_path()
    adjusted = 0
    for region in plan.regions:
        text = region.translation or region.text
        color = _pick_text_color(region.text_color, region.bg_color)
        if color != region.text_color:
            adjusted += 1
        _draw_translated_text(draw, region.box, text, color, font_path)
    if adjusted:
        log(f"  {adjusted} 处译文与底色对比不足，已自动选用对比色")

    rgba = stamp_image(rgba)
    pnginfo = png_text_chunk() if (orig_format or "PNG").upper() in ("PNG",) else None
    fmt = (orig_format or "PNG").upper()
    if fmt in ("JPEG", "JPG"):
        log("  JPEG 无法保留 LSB/PNG 元数据水印，已写入可见水印")

    if rgba.size != orig_size:
        log(f"  尺寸异常 {rgba.size} != {orig_size}")
        return False
    try:
        _save_rgba(rgba, plan.path, orig_format, pnginfo=pnginfo)
        return True
    except Exception as e:
        log(f"  保存图片失败: {e}")
        return False


def _batch_translate_plans(
    plans: list[ImagePlan],
    text_llm_cfg,
    log,
    lang_label: str,
) -> None:
    """步骤 3a：全部文字片段合并批量翻译，再写回各 plan。"""
    flat: list[RegionRecord] = [r for plan in plans for r in plan.regions]
    if not flat:
        return

    all_translations: list[str] = []
    batch_total = (len(flat) + TEXT_BATCH_SIZE - 1) // TEXT_BATCH_SIZE
    for start in range(0, len(flat), TEXT_BATCH_SIZE):
        chunk = flat[start : start + TEXT_BATCH_SIZE]
        texts = [r.text for r in chunk]
        batch_num = start // TEXT_BATCH_SIZE + 1
        batch_label = f"图片文字翻译批次 {batch_num}/{batch_total}（{len(texts)} 条）"
        log(f"  翻译批次 {batch_num}/{batch_total}：{len(texts)} 条")
        translated = translate_image_texts(
            texts, text_llm_cfg, log, lang_label=lang_label, batch_label=batch_label
        )
        if len(translated) != len(texts):
            log(f"  翻译条数不匹配 ({len(translated)}/{len(texts)})，保留原文")
            translated = texts
        all_translations.extend(translated)

    for region, trans in zip(flat, all_translations, strict=True):
        region.translation = trans


def localize_images_ocr_batch(
    image_paths: list[Path],
    text_llm_cfg,
    backup: bool,
    log,
    lang_label: str = "简体中文",
    stop_flag=None,
    on_progress=None,
) -> tuple[int, int]:
    """批量 OCR 擦写：全量 OCR → 全量涂底 → 批量翻译 → 批量写回。"""
    total = len(image_paths)
    if total == 0:
        return 0, 0

    if _get_ocr_engine(log) is None:
        return 0, total

    # 步骤 1：全部 OCR
    log("步骤 1/3：OCR 识别全部图片…")
    plans: list[ImagePlan] = []
    for n, path in enumerate(image_paths, 1):
        if stop_flag is not None and stop_flag.is_set():
            log("已停止")
            break
        log(f"  [{n}/{total}] OCR {path.name}")
        plan = _build_plan(path, log)
        if plan is not None:
            plans.append(plan)

    if not plans:
        log("未识别到任何文字")
        return 0, total

    text_count = sum(len(p.regions) for p in plans)
    log(f"OCR 完成：{len(plans)} 张图，共 {text_count} 处文字")

    # 步骤 2：全部粉刷底色
    log("步骤 2/3：粉刷全部底色…")
    painted = 0
    for n, plan in enumerate(plans, 1):
        if stop_flag is not None and stop_flag.is_set():
            log("已停止")
            break
        log(f"  [{n}/{len(plans)}] 涂底 {plan.path.name}")
        if backup:
            _backup_image(plan.path, log)
        plan.painted = _paint_backgrounds(plan, log)
        if plan.painted:
            painted += 1

    # 步骤 3：批量翻译 + 批量写回
    log("步骤 3/3：批量翻译并写回…")
    _batch_translate_plans(plans, text_llm_cfg, log, lang_label)

    ok = 0
    for n, plan in enumerate(plans, 1):
        if stop_flag is not None and stop_flag.is_set():
            log("已停止")
            break
        if not plan.painted:
            log(f"  [{n}/{len(plans)}] 跳过写回 {plan.path.name}（涂底失败）")
            continue
        log(f"  [{n}/{len(plans)}] 写回 {plan.path.name}")
        if _write_translations(plan, log):
            ok += 1
            log(f"  已 OCR 本地化: {plan.path.name}")
        if on_progress is not None:
            on_progress(n, len(plans))

    return ok, total


def localize_image_ocr(
    image_path: Path,
    text_llm_cfg,
    backup: bool,
    log,
    lang_label: str = "简体中文",
) -> bool:
    """单张图片 OCR 擦写（内部走批量流程）。"""
    ok, _total = localize_images_ocr_batch(
        [image_path], text_llm_cfg, backup, log, lang_label=lang_label
    )
    return ok > 0
