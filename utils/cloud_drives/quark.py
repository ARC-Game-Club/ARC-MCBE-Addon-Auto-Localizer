# -*- coding: utf-8 -*-
"""夸克网盘：网页 Cookie 鉴权，上传到指定文件夹并创建分享链接。"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .base import CloudDrive, CloudDriveError, ConfigField, ShareResult, UploadResult, register

API = "https://drive-pc.quark.cn/1/clouddrive"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OSS_UA = "aliyun-sdk-js/6.6.1 Chrome 98.0.4758.80 on Windows 10 64-bit"


def _gmt_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _merge_cookie(old: str, resp: httpx.Response) -> str:
    puus = resp.cookies.get("__puus")
    if not puus:
        return old
    if "__puus=" in old:
        return re.sub(r"__puus=[^;]*", f"__puus={puus}", old)
    return old.rstrip("; ") + f"; __puus={puus}"


def _oss_url(pre: dict, obj_key: str) -> str:
    bucket = pre.get("bucket") or ""
    raw = str(pre.get("upload_url") or "")
    if "://" in raw:
        host = urlparse(raw).netloc or urlparse(raw).path
    else:
        host = raw.lstrip("/")
    if host.startswith(bucket + "."):
        return f"https://{host}/{obj_key}"
    return f"https://{bucket}.{host}/{obj_key}"


@register
class QuarkDrive(CloudDrive):
    id = "quark"
    display_name = "夸克网盘"
    supports_share = True
    auth_mode = "cookie"
    notes = (
        "没有官方开放平台，走网页接口。在 pan.quark.cn 登录后 F12 → Network "
        "复制任意请求的 Cookie。可自动生成分享链接。"
    )

    @classmethod
    def default_config(cls) -> dict:
        return {
            "enabled": False,
            "cookie": "",
            "parent_fid": "0",
            "share_password": "",
        }

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField("cookie", "Cookie", "password", hint="从 pan.quark.cn 开发者工具复制，不要发到聊天里"),
            ConfigField("parent_fid", "目标文件夹 ID", hint="根目录填 0；打开文件夹后从地址栏复制 fid"),
            ConfigField("share_password", "分享提取码（可空）", hint="留空=公开链接"),
        ]

    def is_authorized(self) -> bool:
        return bool((self.cfg.get("cookie") or "").strip())

    def status_text(self) -> str:
        fid = (self.cfg.get("parent_fid") or "0").strip() or "0"
        if self.is_authorized():
            return f"已填写 Cookie · 上传到文件夹 {fid} · 可自动分享"
        return "未填写 Cookie · 打开 pan.quark.cn 登录后复制"

    def authorize_url(self) -> str:
        return "https://pan.quark.cn/"

    def _headers(self) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://pan.quark.cn",
            "Referer": "https://pan.quark.cn/",
            "User-Agent": UA,
            "Cookie": (self.cfg.get("cookie") or "").strip(),
        }

    def _api(self, client: httpx.Client, path: str, *, method: str = "POST", json_body=None, params=None) -> dict:
        q = {"pr": "ucpro", "fr": "pc"}
        if params:
            q.update(params)
        headers = self._headers()
        if method == "GET":
            resp = client.get(API + path, headers=headers, params=q)
        else:
            headers["Content-Type"] = "application/json"
            resp = client.post(API + path, headers=headers, params=q, json=json_body or {})
        cookie = (self.cfg.get("cookie") or "").strip()
        merged = _merge_cookie(cookie, resp)
        if merged != cookie:
            self.cfg["cookie"] = merged
        try:
            data = resp.json()
        except Exception as exc:
            raise CloudDriveError(f"夸克接口返回非 JSON（HTTP {resp.status_code}）") from exc
        if not isinstance(data, dict):
            raise CloudDriveError(f"夸克接口返回异常: {data!r}")
        if data.get("status", 200) >= 400 or data.get("code", 0) not in (0, None):
            raise CloudDriveError(data.get("message") or f"夸克错误 code={data.get('code')}")
        return data

    def test_connection(self) -> str:
        if not self.is_authorized():
            raise CloudDriveError("请先填写 Cookie")
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            data = self._api(client, "/member", method="GET")
        info = data.get("data") or {}
        return info.get("nickname") or info.get("member_name") or "夸克网盘账号"

    def upload(self, local_path: Path, log=None) -> UploadResult:
        local_path = Path(local_path)
        if not local_path.is_file():
            raise CloudDriveError(f"文件不存在: {local_path}")
        if not self.is_authorized():
            raise CloudDriveError("请先填写夸克 Cookie")

        def _log(msg: str) -> None:
            if log:
                log(msg)

        parent = (self.cfg.get("parent_fid") or "0").strip() or "0"
        mime, _ = mimetypes.guess_type(local_path.name)
        mime = mime or "application/octet-stream"
        size = local_path.stat().st_size
        _log(f"上传到夸克网盘: {local_path.name}（{size // 1024} KB）")

        md5 = hashlib.md5()
        sha1 = hashlib.sha1()
        with local_path.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                md5.update(chunk)
                sha1.update(chunk)

        now_ms = int(time.time() * 1000)
        with httpx.Client(timeout=180, follow_redirects=True) as client:
            pre_full = self._api(
                client,
                "/file/upload/pre",
                json_body={
                    "ccp_hash_update": True,
                    "dir_name": "",
                    "file_name": local_path.name,
                    "format_type": mime,
                    "l_created_at": now_ms,
                    "l_updated_at": now_ms,
                    "pdir_fid": parent,
                    "size": size,
                },
            )
            pre = pre_full.get("data") or {}
            meta = pre_full.get("metadata") or {}
            task_id = pre.get("task_id")
            if not task_id:
                raise CloudDriveError("预上传未返回 task_id，Cookie 可能已过期")

            hashed = self._api(
                client,
                "/file/update/hash",
                json_body={"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "task_id": task_id},
            )
            if (hashed.get("data") or {}).get("finish"):
                _log("夸克秒传成功")
            else:
                part_size = int(pre.get("part_size") or meta.get("part_size") or 20 * 1024 * 1024)
                etags = self._upload_parts(client, pre, local_path, mime, part_size, log=_log)
                self._commit_parts(client, pre, etags)
                self._api(client, "/file/upload/finish", json_body={"obj_key": pre.get("obj_key"), "task_id": task_id})
                _log("夸克分片上传完成")

            fid = str(pre.get("fid") or (hashed.get("data") or {}).get("fid") or "")
            if not fid:
                raise CloudDriveError("上传成功但未返回文件 ID")
        label = f"{local_path.name}（fid {fid}）"
        _log(f"夸克网盘上传完成: {label}")
        return UploadResult(remote_id=fid, remote_label=label, extra={"name": local_path.name})

    def _upload_auth(self, client: httpx.Client, pre: dict, auth_meta: str) -> str:
        data = self._api(
            client,
            "/file/upload/auth",
            json_body={"auth_info": pre.get("auth_info"), "auth_meta": auth_meta, "task_id": pre.get("task_id")},
        )
        key = (data.get("data") or {}).get("auth_key")
        if not key:
            raise CloudDriveError("未获得 OSS 上传授权")
        return key

    def _upload_parts(self, client, pre, path: Path, mime: str, part_size: int, log=None) -> list[str]:
        etags = []
        part = 1
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(part_size)
                if not chunk:
                    break
                now = _gmt_now()
                auth_meta = (
                    f"PUT\n\n{mime}\n{now}\n"
                    f"x-oss-date:{now}\n"
                    f"x-oss-user-agent:{OSS_UA}\n"
                    f"/{pre['bucket']}/{pre['obj_key']}?partNumber={part}&uploadId={pre['upload_id']}"
                )
                auth_key = self._upload_auth(client, pre, auth_meta)
                resp = client.put(
                    _oss_url(pre, pre["obj_key"]),
                    params={"partNumber": str(part), "uploadId": pre["upload_id"]},
                    headers={
                        "Authorization": auth_key,
                        "Content-Type": mime,
                        "Referer": "https://pan.quark.cn/",
                        "x-oss-date": now,
                        "x-oss-user-agent": OSS_UA,
                    },
                    content=chunk,
                )
                if resp.status_code != 200:
                    raise CloudDriveError(f"夸克分片 {part} 上传失败 HTTP {resp.status_code}")
                etags.append(resp.headers.get("ETag") or "")
                if log:
                    log(f"  已上传夸克分片 {part}")
                part += 1
        return etags

    def _commit_parts(self, client, pre, etags: list[str]) -> None:
        parts_xml = "".join(
            f"<Part><PartNumber>{i}</PartNumber><ETag>{etag}</ETag></Part>"
            for i, etag in enumerate(etags, 1)
        )
        xml_body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<CompleteMultipartUpload>{parts_xml}</CompleteMultipartUpload>"
        )
        raw = xml_body.encode("utf-8")
        content_md5 = base64.b64encode(hashlib.md5(raw).digest()).decode("ascii")
        callback_b64 = base64.b64encode(json.dumps(pre.get("callback") or {}).encode("utf-8")).decode("ascii")
        now = _gmt_now()
        auth_meta = (
            f"POST\n{content_md5}\napplication/xml\n{now}\n"
            f"x-oss-callback:{callback_b64}\n"
            f"x-oss-date:{now}\n"
            f"x-oss-user-agent:{OSS_UA}\n"
            f"/{pre['bucket']}/{pre['obj_key']}?uploadId={pre['upload_id']}"
        )
        auth_key = self._upload_auth(client, pre, auth_meta)
        resp = client.post(
            _oss_url(pre, pre["obj_key"]),
            params={"uploadId": pre["upload_id"]},
            headers={
                "Authorization": auth_key,
                "Content-MD5": content_md5,
                "Content-Type": "application/xml",
                "Referer": "https://pan.quark.cn/",
                "x-oss-callback": callback_b64,
                "x-oss-date": now,
                "x-oss-user-agent": OSS_UA,
            },
            content=raw,
        )
        if resp.status_code != 200:
            raise CloudDriveError(f"夸克合并分片失败 HTTP {resp.status_code}")

    def share(self, uploaded: UploadResult, log=None) -> ShareResult:
        def _log(msg: str) -> None:
            if log:
                log(msg)

        password = (self.cfg.get("share_password") or "").strip()
        body = {
            "fid_list": [uploaded.remote_id],
            "title": uploaded.extra.get("name") or uploaded.remote_label,
            "url_type": 2 if password else 1,
            "expired_type": 1,
        }
        if password:
            body["passcode"] = password
        _log("正在创建夸克分享链接 …")
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            created = self._api(client, "/share", json_body=body)
            task_id = (created.get("data") or {}).get("task_id")
            if not task_id:
                raise CloudDriveError("创建分享未返回 task_id")
            share_id = ""
            for _ in range(20):
                task = self._api(client, "/task", method="GET", params={"task_id": task_id, "retry_index": "0"})
                info = task.get("data") or {}
                status = info.get("status")
                if status == 2:
                    share_id = info.get("share_id") or ""
                    break
                if status in (3, 4):
                    raise CloudDriveError(f"创建分享失败 status={status}")
                time.sleep(0.8)
            if not share_id:
                raise CloudDriveError("等待分享完成超时")
            detail = self._api(client, "/share/password", json_body={"share_id": share_id})
            data = detail.get("data") or {}
        url = data.get("share_url") or ""
        code = data.get("passcode") or data.get("password") or password
        if not url:
            raise CloudDriveError("未返回分享链接")
        _log(f"夸克分享: {url}" + (f"  提取码 {code}" if code else ""))
        return ShareResult(url=url, password=code)
