# -*- coding: utf-8 -*-
"""百度网盘：官方 OAuth，上传到 /apps/<应用名>/。个人应用不能自动分享。"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .base import CloudDrive, CloudDriveError, ConfigField, UploadResult, register

OPENAPI = "https://openapi.baidu.com"
PAN = "https://pan.baidu.com"
PCS = "https://d.pcs.baidu.com"
CHUNK = 4 * 1024 * 1024
REDIRECT_URI = "oob"
SCOPE = "basic,netdisk"
UA = "arc-mcbe-localizer/1.0"


def _client(timeout: float = 60) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True)


def _as_json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception as exc:
        raise CloudDriveError(f"接口返回非 JSON（HTTP {resp.status_code}）") from exc
    if not isinstance(data, dict):
        raise CloudDriveError(f"接口返回异常: {data!r}")
    if data.get("error"):
        raise CloudDriveError(data.get("error_description") or data.get("error"))
    errno = data.get("errno")
    if errno is None:
        errno = data.get("error_code")
    if errno not in (None, 0):
        msg = data.get("errmsg") or data.get("error_msg") or f"errno={errno}"
        raise CloudDriveError(f"{msg}（{errno}）")
    return data


def _remote_path(app_name: str, remote_dir: str, filename: str) -> str:
    parts = ["apps", (app_name or "").strip().strip("/")]
    if not parts[1]:
        raise CloudDriveError("请先填写与开放平台一致的应用名称")
    sub = (remote_dir or "").strip().replace("\\", "/").strip("/")
    if sub:
        parts.extend(p for p in sub.split("/") if p and p != "..")
    parts.append(Path(filename).name)
    return "/" + "/".join(parts)


def _display_path(api_path: str) -> str:
    p = (api_path or "").lstrip("/")
    if p.lower().startswith("apps/"):
        p = p[5:]
    return "我的应用数据/" + p


@register
class BaiduDrive(CloudDrive):
    id = "baidu"
    display_name = "百度网盘"
    supports_share = False
    auth_mode = "oauth_code"
    notes = "官方接口只能传到「我的应用数据 / 应用名称」。个人应用不能自动创建分享链接。"

    @classmethod
    def default_config(cls) -> dict:
        return {
            "enabled": False,
            "app_id": "",
            "app_key": "",
            "secret_key": "",
            "app_name": "弧光我的世界基岩汉化",
            "remote_dir": "",
            "access_token": "",
            "refresh_token": "",
            "expires_at": 0,
        }

    def config_fields(self) -> list[ConfigField]:
        return [
            ConfigField("app_name", "应用名称（必须与开放平台完全一致）", hint="决定网盘目录：我的应用数据 / 应用名称"),
            ConfigField("app_key", "AppKey", "password"),
            ConfigField("secret_key", "SecretKey", "password"),
            ConfigField("remote_dir", "子目录（可空，相对应用目录）", hint="例如 2026"),
        ]

    def is_authorized(self) -> bool:
        return bool((self.cfg.get("refresh_token") or self.cfg.get("access_token") or "").strip())

    def status_text(self) -> str:
        name = (self.cfg.get("app_name") or "").strip() or "（未填应用名）"
        dest = f"我的应用数据/{name}/" + ((self.cfg.get("remote_dir") or "").strip() or "")
        if self.is_authorized():
            return f"已授权 · 上传到 {dest}"
        return f"未授权 · 目标 {dest}"

    def authorize_url(self) -> str:
        app_key = (self.cfg.get("app_key") or "").strip()
        if not app_key:
            raise CloudDriveError("请先填写 AppKey")
        q = urlencode(
            {
                "response_type": "code",
                "client_id": app_key,
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPE,
                "display": "popup",
            }
        )
        return f"{OPENAPI}/oauth/2.0/authorize?{q}"

    def _save_token(self, payload: dict) -> None:
        self.cfg["access_token"] = payload.get("access_token") or ""
        if payload.get("refresh_token"):
            self.cfg["refresh_token"] = payload["refresh_token"]
        self.cfg["expires_at"] = int(time.time()) + int(payload.get("expires_in") or 2592000)

    def exchange_code(self, code: str) -> None:
        code = (code or "").strip()
        if not code:
            raise CloudDriveError("请粘贴授权码")
        app_key = (self.cfg.get("app_key") or "").strip()
        secret = (self.cfg.get("secret_key") or "").strip()
        if not app_key or not secret:
            raise CloudDriveError("请先填写 AppKey 和 SecretKey")
        with _client() as client:
            resp = client.get(
                f"{OPENAPI}/oauth/2.0/token",
                params={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": app_key,
                    "client_secret": secret,
                    "redirect_uri": REDIRECT_URI,
                },
            )
            self._save_token(_as_json(resp))
        if not self.cfg.get("access_token"):
            raise CloudDriveError("授权成功但未返回 access_token")

    def _access_token(self) -> str:
        token = (self.cfg.get("access_token") or "").strip()
        expires_at = int(self.cfg.get("expires_at") or 0)
        if token and expires_at > int(time.time()) + 60:
            return token
        refresh = (self.cfg.get("refresh_token") or "").strip()
        app_key = (self.cfg.get("app_key") or "").strip()
        secret = (self.cfg.get("secret_key") or "").strip()
        if not refresh:
            raise CloudDriveError("尚未授权百度网盘，请先在设置里完成授权")
        with _client() as client:
            resp = client.get(
                f"{OPENAPI}/oauth/2.0/token",
                params={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": app_key,
                    "client_secret": secret,
                },
            )
            self._save_token(_as_json(resp))
        token = (self.cfg.get("access_token") or "").strip()
        if not token:
            raise CloudDriveError("刷新授权失败，请重新授权")
        return token

    def test_connection(self) -> str:
        token = self._access_token()
        with _client() as client:
            info = _as_json(
                client.get(
                    f"{PAN}/rest/2.0/xpan/nas",
                    params={"method": "uinfo", "access_token": token},
                )
            )
        return info.get("baidu_name") or info.get("netdisk_name") or "百度网盘账号"

    def upload(self, local_path: Path, log=None) -> UploadResult:
        local_path = Path(local_path)
        if not local_path.is_file():
            raise CloudDriveError(f"文件不存在: {local_path}")

        def _log(msg: str) -> None:
            if log:
                log(msg)

        token = self._access_token()
        remote = _remote_path(self.cfg.get("app_name") or "", self.cfg.get("remote_dir") or "", local_path.name)
        blocks, content_md5, slice_md5, size = _md5_blocks(local_path)
        block_json = json.dumps(blocks, separators=(",", ":"))
        _log(f"上传到百度网盘: {_display_path(remote)}（{size // 1024} KB）")

        with _client(timeout=180) as client:
            pre = _as_json(
                client.post(
                    f"{PAN}/rest/2.0/xpan/file",
                    params={"method": "precreate", "access_token": token},
                    data={
                        "path": remote,
                        "size": str(size),
                        "isdir": "0",
                        "autoinit": "1",
                        "rtype": "3",
                        "block_list": block_json,
                        "content-md5": content_md5,
                        "slice-md5": slice_md5,
                    },
                )
            )
            upload_id = str(pre.get("uploadid") or "").strip()
            missing = _missing_parts(pre, len(blocks))
            if upload_id and missing:
                hosts = _locate_hosts(client, token, remote, upload_id)
                with local_path.open("rb") as fh:
                    for idx in missing:
                        fh.seek(idx * CHUNK)
                        chunk = fh.read(CHUNK)
                        last_err = None
                        for host in hosts:
                            try:
                                _as_json(
                                    client.post(
                                        f"{host}/rest/2.0/pcs/superfile2",
                                        params={
                                            "method": "upload",
                                            "access_token": token,
                                            "type": "tmpfile",
                                            "path": remote,
                                            "uploadid": upload_id,
                                            "partseq": str(idx),
                                        },
                                        files={"file": (local_path.name, chunk)},
                                    )
                                )
                                last_err = None
                                break
                            except Exception as exc:
                                last_err = exc
                        if last_err:
                            raise CloudDriveError(f"分片 {idx} 上传失败: {last_err}")
                        _log(f"  已上传分片 {idx + 1}/{len(blocks)}")
            if upload_id:
                created = _as_json(
                    client.post(
                        f"{PAN}/rest/2.0/xpan/file",
                        params={"method": "create", "access_token": token},
                        data={
                            "path": remote,
                            "size": str(size),
                            "isdir": "0",
                            "rtype": "3",
                            "uploadid": upload_id,
                            "block_list": block_json,
                        },
                    )
                )
                remote = created.get("path") or remote
            elif pre.get("return_type") not in (2, "2"):
                raise CloudDriveError("预上传未返回 uploadid，请检查应用名称是否与开放平台完全一致")
        label = _display_path(remote)
        _log(f"百度网盘上传完成: {label}")
        return UploadResult(remote_id=remote, remote_label=label)


def _md5_blocks(path: Path) -> tuple[list[str], str, str, int]:
    size = path.stat().st_size
    blocks: list[str] = []
    whole = hashlib.md5()
    first = b""
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            if not first:
                first = chunk[: min(256 * 1024, len(chunk))]
            whole.update(chunk)
            blocks.append(hashlib.md5(chunk).hexdigest())
    if size == 0:
        blocks = [hashlib.md5(b"").hexdigest()]
        first = b""
    return blocks, whole.hexdigest(), hashlib.md5(first).hexdigest(), size


def _missing_parts(payload, total: int) -> list[int]:
    raw = payload.get("block_list")
    if raw in (None, "", []):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return list(range(total))
    if isinstance(raw, list) and raw and all(isinstance(x, int) or str(x).isdigit() for x in raw):
        return [int(x) for x in raw]
    return list(range(total))


def _locate_hosts(client: httpx.Client, token: str, remote: str, upload_id: str) -> list[str]:
    hosts = []
    try:
        data = client.get(
            f"{PCS}/rest/2.0/pcs/file",
            params={
                "method": "locateupload",
                "access_token": token,
                "path": remote,
                "uploadid": upload_id,
                "upload_version": "2.0",
            },
        ).json()
        if isinstance(data, dict):
            for item in data.get("servers") or []:
                server = str((item or {}).get("server") or "").rstrip("/")
                if server.startswith("https://"):
                    hosts.append(server)
            host = str(data.get("host") or "").strip()
            if host:
                hosts.append(f"https://{host}")
    except Exception:
        pass
    hosts.append(PCS)
    seen: set[str] = set()
    out = []
    for h in hosts:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out
