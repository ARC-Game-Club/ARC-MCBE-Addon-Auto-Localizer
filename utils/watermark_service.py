# -*- coding: utf-8 -*-
"""本地化图片水印：右下角明水印 + LSB 隐写 + PNG 元数据。"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from .languages import TOOL_NAME_HAN, TOOL_NAME_LATIN

WATERMARK_TEXT = TOOL_NAME_HAN
WATERMARK_MAGIC = b"ARCLOC1"
MIN_VISIBLE_SIZE = 64
VISIBLE_ALPHA = 90


def _encode_payload(text: str) -> bytes:
    body = text.encode("utf-8")
    return WATERMARK_MAGIC + len(body).to_bytes(4, "big") + body


def _bits_to_bytes(bits: list[int], byte_count: int) -> bytes:
    out = bytearray()
    for i in range(byte_count):
        val = 0
        for b in range(8):
            val = (val << 1) | bits[i * 8 + b]
        out.append(val)
    return bytes(out)


def _extract_lsb(arr: np.ndarray) -> bytes | None:
    flat = arr.reshape(-1, 4)
    max_bytes = len(WATERMARK_MAGIC) + 4 + 512
    max_bits = min(len(flat), max_bytes * 8)
    if max_bits < 8:
        return None
    bits = [int(flat[i, 0]) & 1 for i in range(max_bits)]
    for length in range(len(WATERMARK_MAGIC), max_bytes + 1):
        chunk = _bits_to_bytes(bits, length)
        if chunk.startswith(WATERMARK_MAGIC):
            if len(chunk) < len(WATERMARK_MAGIC) + 4:
                continue
            body_len = int.from_bytes(
                chunk[len(WATERMARK_MAGIC) : len(WATERMARK_MAGIC) + 4], "big"
            )
            total = len(WATERMARK_MAGIC) + 4 + body_len
            if body_len <= 512 and len(bits) >= total * 8:
                return _bits_to_bytes(bits, total)
    return None


def _embed_lsb(arr: np.ndarray, payload: bytes) -> np.ndarray:
    flat_len = arr.size // 4
    if len(payload) * 8 > flat_len:
        return arr
    out = arr.copy()
    flat = out.reshape(-1, 4)
    bit_idx = 0
    for byte in payload:
        for bit in range(8):
            if bit_idx >= len(flat):
                return out
            ch = int(flat[bit_idx, 0])
            flat[bit_idx, 0] = (ch & 0xFE) | ((byte >> (7 - bit)) & 1)
            bit_idx += 1
    return out


def _find_font_path() -> str | None:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def _draw_visible_watermark(rgba):
    from PIL import Image, ImageDraw, ImageFont

    w, h = rgba.size
    if w < MIN_VISIBLE_SIZE or h < MIN_VISIBLE_SIZE:
        return rgba

    size = max(8, min(20, int(h * 0.035)))
    font_path = _find_font_path()
    try:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    except OSError:
        font = ImageFont.load_default()

    overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    text = WATERMARK_TEXT
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = max(0, w - tw - 2)
    y = max(0, h - th - 2)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, VISIBLE_ALPHA))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, VISIBLE_ALPHA))
    return Image.alpha_composite(rgba, overlay)


def has_watermark_array(arr: np.ndarray) -> bool:
    payload = _extract_lsb(arr)
    if payload and WATERMARK_MAGIC in payload:
        return True
    return False


def read_watermark_from_info(info: dict | None) -> str | None:
    if not info:
        return None
    for key in ("Localization", "Software"):
        val = info.get(key)
        if isinstance(val, str) and WATERMARK_TEXT in val:
            return WATERMARK_TEXT
        if isinstance(val, bytes):
            try:
                text = val.decode("utf-8", errors="ignore")
                if WATERMARK_TEXT in text:
                    return WATERMARK_TEXT
            except Exception:
                pass
    return None


def read_watermark(path: Path | str) -> str | None:
    """从文件读取 LSB 或 PNG 元数据水印。"""
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.load()
            meta = read_watermark_from_info(im.info)
            if meta:
                return meta
            arr = np.array(im.convert("RGBA"))
            if has_watermark_array(arr):
                return WATERMARK_TEXT
    except Exception:
        pass
    return None


def png_text_chunk():
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Software", f"{TOOL_NAME_HAN} / {TOOL_NAME_LATIN}")
    info.add_text("Localization", WATERMARK_TEXT)
    return info


def stamp_image(img):
    """明水印 + LSB 隐写；已有水印则跳过。"""
    from PIL import Image

    rgba = img.convert("RGBA")
    arr = np.array(rgba)
    if has_watermark_array(arr):
        return rgba
    meta = read_watermark_from_info(getattr(img, "info", None))
    if meta:
        return rgba

    rgba = _draw_visible_watermark(rgba)
    arr = np.array(rgba)
    arr = _embed_lsb(arr, _encode_payload(WATERMARK_TEXT))
    return Image.fromarray(arr, "RGBA")


def stamp_bytes(data: bytes, log, suffix: str = ".png") -> bytes:
    """对图片字节打水印；JPEG 仅保留可见水印。"""
    from PIL import Image

    buf_in = io.BytesIO(data)
    with Image.open(buf_in) as im:
        im.load()
        fmt = (im.format or "PNG").upper()
        stamped = stamp_image(im)
        buf_out = io.BytesIO()
        if fmt in ("JPEG", "JPG"):
            log("  JPEG 无法保留 LSB/PNG 元数据水印，已写入可见水印")
            stamped.convert("RGB").save(buf_out, format="JPEG")
        elif fmt == "PNG":
            stamped.save(buf_out, format="PNG", pnginfo=png_text_chunk(), optimize=True)
        elif fmt == "BMP":
            stamped.save(buf_out, format="BMP")
            log("  BMP 已写入 LSB 隐写水印")
        else:
            if fmt == "WEBP":
                log("  WebP 无法保留 LSB/PNG 元数据，已写入可见水印")
            stamped.save(buf_out, format=fmt)
        return buf_out.getvalue()
