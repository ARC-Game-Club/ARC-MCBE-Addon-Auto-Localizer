# -*- coding: utf-8 -*-
"""LLM 客户端与文本 / 图片翻译服务。

所有函数通过 openai 库调用 OpenAI 兼容接口，
文本与图片翻译共用一套 llm_cfg 结构：{base_url, api_key, model, proxy}。
proxy 留空则直连；填写 host:port 或带协议的 URL 则走代理。
"""
import base64
import re
import shutil
import urllib.request
from pathlib import Path

from .text_utils import extract_urls


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

LANG_TRANSLATE_PROMPT = """你是一名专业的 Minecraft 基岩版模组汉化专家。
请将下面的 .lang 语言文件内容翻译为简体中文。

规则：
1. 保持每行格式为 键=翻译后的中文值，一行一条，行数与输入完全一致
2. 只翻译等号右边的文字，等号左边的键原样保留
3. 保留 %s、%1、§c、\\n 等占位符、格式代码、颜色代码完全不变
4. 实体名、物品名、技能名使用游戏内通用中文译名
5. 如果值已经是中文或纯符号，保持不变
6. 不要输出任何解释、前言、结尾，只输出翻译后的行

待翻译内容：
{batch}
"""

IMAGE_TRANSLATE_PROMPT = (
    "保持图片格式和已有图案不变，汉化图片，将图片上的英文改为中文。"
    "请直接返回汉化后的图片本身，不要附加任何文字说明。"
)


def make_client(llm_cfg):
    """构造 OpenAI 兼容客户端；llm_cfg.proxy 非空时经该代理访问。"""
    import openai
    kwargs = {
        "base_url": (llm_cfg.get("base_url") or None),
        "api_key": (llm_cfg.get("api_key") or ""),
    }
    proxy = normalize_proxy(llm_cfg.get("proxy"))
    if proxy:
        kwargs["http_client"] = _httpx_client(proxy)
    return openai.OpenAI(**kwargs)


def translate_lang_batch(entries, llm_cfg, log) -> dict:
    """
    翻译一批 [(key, value)]，返回 {key: translated}。
    失败时保留原值，不中断整体流程。
    """
    batch_text = "\n".join(f"{k}={v}" for k, v in entries)
    prompt = LANG_TRANSLATE_PROMPT.format(batch=batch_text)
    result = {}
    try:
        client = make_client(llm_cfg)
        resp = client.chat.completions.create(
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


def translate_text(text_llm_cfg, prompt, log) -> str:
    """通用文本补全，用于 display_name 等翻译。失败时抛出异常。"""
    try:
        client = make_client(text_llm_cfg)
        resp = client.chat.completions.create(
            model=text_llm_cfg.get("model"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        log(f"LLM 调用失败: {e}")
        raise


def translate_image_file(image_path: Path, image_llm_cfg, backup: bool, log) -> bool:
    """调用图片 LLM 汉化单张图片，返回是否成功。"""
    try:
        import openai
    except ImportError:
        log("未安装 openai，请先执行: pip install openai")
        return False

    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
    except OSError as e:
        log(f"读取图片失败: {e}")
        return False

    suffix = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")

    try:
        client = make_client(image_llm_cfg)
        resp = client.chat.completions.create(
            model=image_llm_cfg.get("model"),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": IMAGE_TRANSLATE_PROMPT},
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
