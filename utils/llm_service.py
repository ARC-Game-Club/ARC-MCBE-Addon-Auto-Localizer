# -*- coding: utf-8 -*-
"""LLM 客户端与文本 / 图片翻译服务。

所有函数通过 openai 库调用 OpenAI 兼容接口，
文本与图片翻译共用一套 llm_cfg 结构：{base_url, api_key, model, proxy}。
proxy 留空则直连；填写 host:port 或带协议的 URL 则走代理。
"""
import base64
import re
import shutil
import threading
import time
import urllib.request
from pathlib import Path

from .text_utils import extract_urls
from .watermark_service import stamp_bytes

HEARTBEAT_SEC = 15


def normalize_proxy(proxy) -> str:
    """将用户填写的代理规范化为带协议的 URL；空则返回空串。"""
    proxy = (proxy or "").strip()
    if not proxy:
        return ""
    if "://" not in proxy:
        proxy = "http://" + proxy
    return proxy


def _httpx_client(proxy_url: str):
    """按 httpx 版本差异构造带代理的 Client。"""
    import httpx
    try:
        return httpx.Client(proxy=proxy_url)
    except TypeError:
        return httpx.Client(proxies=proxy_url)

LANG_TRANSLATE_PROMPT = """你是一名专业的 Minecraft 基岩版模组本地化专家。
请将下面的 .lang 语言文件内容翻译为{lang_label}。

规则：
1. 保持每行格式为 键=翻译后的值，一行一条，行数与输入完全一致
2. 只翻译等号右边的文字，等号左边的键原样保留
3. 保留 %s、%1、§c、\\n 等占位符、格式代码、颜色代码完全不变
4. 实体名、物品名、技能名使用游戏内通用的{lang_label}译名
5. 如果值已经是{lang_label}或纯符号，保持不变
6. 不要输出任何解释、前言、结尾，只输出翻译后的行

待翻译内容：
{batch}
"""

IMAGE_TRANSLATE_PROMPT = (
    "保持图片格式、画幅比例和已有图案不变，只将图上的英文改成{lang_label}。"
    "输出图片的像素宽高必须与输入完全一致（不要裁剪、不要改画幅、不要缩放画布）。"
    "请直接返回本地化后的图片本身，不要附加任何文字说明。"
)

IMAGE_TEXTS_TRANSLATE_PROMPT = """你是一名专业的 Minecraft 基岩版模组本地化专家。
请将下面编号列出的图片文字片段翻译为{lang_label}。

规则：
1. 保持编号与行数完全一致，格式为「编号. 译文」
2. 只翻译文字内容，保留数字、符号、专有名词的合理译法
3. 每条译文尽量简洁，适合写回图片原位置
4. 如果原文已是{lang_label}或纯符号，保持不变
5. 不要输出任何解释、前言、结尾

待翻译内容：
{batch}
"""


def _image_size(raw: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(raw)) as im:
            return im.size
    except Exception:
        return None


def _fit_image_bytes_to_size(data: bytes, width: int, height: int, log) -> bytes:
    """把模型输出强制缩放到原图像素尺寸，尽量保留透明通道。"""
    from PIL import Image
    import io

    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.size == (width, height):
            return data
        log(f"  模型输出 {im.size[0]}×{im.size[1]}，已缩放回原分辨率 {width}×{height}")
        # 游戏贴图多为像素风，用最近邻避免发糊
        resized = im.resize((width, height), Image.Resampling.NEAREST)
        fmt = (im.format or "PNG").upper()
        if fmt not in {"PNG", "JPEG", "JPG", "WEBP", "BMP"}:
            fmt = "PNG"
        if fmt in {"JPG", "JPEG"} and resized.mode in ("RGBA", "P", "LA"):
            resized = resized.convert("RGB")
            fmt = "JPEG"
        buf = io.BytesIO()
        save_kw = {}
        if fmt == "PNG":
            save_kw["optimize"] = True
        resized.save(buf, format="JPEG" if fmt == "JPG" else fmt, **save_kw)
        return buf.getvalue()


def make_client(llm_cfg):
    """构造 OpenAI 兼容客户端；llm_cfg.proxy 非空时经该代理访问。"""
    import httpx
    import openai
    kwargs = {
        "base_url": (llm_cfg.get("base_url") or None),
        "api_key": (llm_cfg.get("api_key") or ""),
    }
    proxy = normalize_proxy(llm_cfg.get("proxy"))
    http_client = _httpx_client(proxy) if proxy else httpx.Client(
        timeout=httpx.Timeout(300.0, connect=30.0)
    )
    if proxy:
        http_client.timeout = httpx.Timeout(300.0, connect=30.0)
    kwargs["http_client"] = http_client
    return openai.OpenAI(**kwargs)


def chat_completion_with_status(client, log, label: str, **create_kwargs):
    """带等待心跳日志的 chat.completions.create 包装。"""
    model = create_kwargs.get("model") or "?"
    log(f"  → 正在请求 {label}（模型 {model}）…")

    done = threading.Event()
    holder: dict = {"resp": None, "error": None}

    def worker():
        try:
            holder["resp"] = client.chat.completions.create(**create_kwargs)
        except Exception as e:
            holder["error"] = e
        finally:
            done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    start = time.monotonic()
    while not done.wait(HEARTBEAT_SEC):
        elapsed = int(time.monotonic() - start)
        log(f"  … 仍在等待 {label} 响应（已 {elapsed}s，请勿关闭窗口）")

    if holder["error"] is not None:
        raise holder["error"]
    elapsed = int(time.monotonic() - start)
    log(f"  ← {label} 响应已返回（耗时 {elapsed}s）")
    return holder["resp"]


def translate_lang_batch(
    entries,
    llm_cfg,
    log,
    lang_label: str = "简体中文",
    batch_label: str | None = None,
) -> dict:
    """
    翻译一批 [(key, value)]，返回 {key: translated}。
    失败时保留原值，不中断整体流程。
    """
    batch_text = "\n".join(f"{k}={v}" for k, v in entries)
    prompt = LANG_TRANSLATE_PROMPT.format(batch=batch_text, lang_label=lang_label)
    label = batch_label or f"语言翻译（{len(entries)} 条）"
    result = {}
    try:
        client = make_client(llm_cfg)
        resp = chat_completion_with_status(
            client,
            log,
            label,
            model=llm_cfg.get("model"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        out = resp.choices[0].message.content or ""
    except Exception as e:
        log(f"  翻译批次失败: {e}")
        return {k: v for k, v in entries}

    keys = {k for k, _ in entries}
    for line in out.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k in keys and v.strip():
            result[k] = v.strip()
    for k, v in entries:
        result.setdefault(k, v)
    return result


def translate_image_texts(
    texts: list[str],
    text_llm_cfg,
    log,
    lang_label: str = "简体中文",
    batch_label: str | None = None,
) -> list[str]:
    """批量翻译 OCR 提取的文字片段；失败时返回原文。"""
    if not texts:
        return []
    batch_text = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = IMAGE_TEXTS_TRANSLATE_PROMPT.format(batch=batch_text, lang_label=lang_label)
    label = batch_label or f"图片文字翻译（{len(texts)} 条）"
    try:
        client = make_client(text_llm_cfg)
        resp = chat_completion_with_status(
            client,
            log,
            label,
            model=text_llm_cfg.get("model"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        out = resp.choices[0].message.content or ""
    except Exception as e:
        log(f"  图片文字翻译失败: {e}")
        return list(texts)

    result: dict[int, str] = {}
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^(\d+)\.\s*(.+)$", line)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(texts) and m.group(2).strip():
            result[idx] = m.group(2).strip()

    return [result.get(i, texts[i]) for i in range(len(texts))]


def translate_text(text_llm_cfg, prompt, log, label: str = "LLM 补全") -> str:
    """通用文本补全，用于 display_name 等翻译。失败时抛出异常。"""
    try:
        client = make_client(text_llm_cfg)
        resp = chat_completion_with_status(
            client,
            log,
            label,
            model=text_llm_cfg.get("model"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        log(f"LLM 调用失败: {e}")
        raise


def translate_image_file(
    image_path: Path,
    image_llm_cfg,
    backup: bool,
    log,
    lang_label: str = "简体中文",
) -> bool:
    """调用图片 LLM 本地化单张图片，返回是否成功；写回时强制保持原分辨率。"""
    try:
        import openai  # noqa: F401
    except ImportError:
        log("未安装 openai，请先执行: pip install openai")
        return False

    try:
        with open(image_path, "rb") as f:
            raw = f.read()
            b64 = base64.b64encode(raw).decode("utf-8")
    except OSError as e:
        log(f"读取图片失败: {e}")
        return False

    orig_size = _image_size(raw)
    suffix = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(suffix, "image/png")

    base_prompt = IMAGE_TRANSLATE_PROMPT.format(lang_label=lang_label)
    prompt = base_prompt
    if orig_size:
        w, h = orig_size
        prompt = (
            f"{base_prompt}"
            f"输入图分辨率是 {w}×{h} 像素；输出也必须是 {w}×{h} 像素。"
        )
        log(f"  原图尺寸: {w}×{h}")

    try:
        client = make_client(image_llm_cfg)
        resp = chat_completion_with_status(
            client,
            log,
            f"图片翻译 {image_path.name}",
            model=image_llm_cfg.get("model"),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except Exception as e:
        log(f"API 调用失败: {e}")
        return False

    data = extract_image_from_response(
        resp, log, proxy=normalize_proxy(image_llm_cfg.get("proxy")))
    if data is None:
        return False

    if orig_size:
        try:
            data = _fit_image_bytes_to_size(data, orig_size[0], orig_size[1], log)
        except Exception as e:
            log(f"  分辨率校正失败: {e}")
            return False

    try:
        data = stamp_bytes(data, log, suffix=image_path.suffix)
    except Exception as e:
        log(f"  水印写入失败: {e}")
        return False

    if backup:
        backup_dir = image_path.parent / "_backup"
        try:
            backup_dir.mkdir(exist_ok=True)
            shutil.copy2(str(image_path), str(backup_dir / image_path.name))
            log(f"  已备份原图到 {backup_dir.name}/")
        except OSError as e:
            log(f"  备份失败: {e}")

    try:
        with open(image_path, "wb") as f:
            f.write(data)
        log(f"  已翻译: {image_path.name}")
        return True
    except OSError as e:
        log(f"  写入图片失败: {e}")
        return False


def extract_image_from_response(resp, log, proxy=""):
    """从 chat.completions 响应中提取图片字节，兼容多种返回格式。"""
    msg = resp.choices[0].message
    content = msg.content
    parts = []

    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        for p in content:
            if isinstance(p, dict):
                if p.get("type") == "text" and isinstance(p.get("text"), str):
                    parts.append(p["text"])
                if p.get("type") == "image_url":
                    parts.append(p["image_url"].get("url", ""))

    opener = urllib.request.build_opener()
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))

    for part in parts:
        if isinstance(part, str):
            m = re.search(r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=]+)", part)
            if m:
                try:
                    return base64.b64decode(m.group(1))
                except Exception as e:
                    log(f"  base64 解码失败: {e}")
            for url in extract_urls(part):
                if "://" in url:
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                        with opener.open(req, timeout=60) as r:
                            return r.read()
                    except Exception as e:
                        log(f"  下载图片失败: {url[:60]} ({e})")
    log("  未能从模型响应中提取图片（可能模型不支持图片输出）")
    return None
