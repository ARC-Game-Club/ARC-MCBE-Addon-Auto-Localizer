# -*- coding: utf-8 -*-
"""图片本地化页：按目录预览、勾选后本地化，写回保持原分辨率。"""
from __future__ import annotations

import io
from pathlib import Path

import flet as ft

from ..languages import DEFAULT_CODE, label_of
from ..llm_service import translate_image_file
from .base_tab import BaseTab
from .components import confirm, error_toast, toast
from .theme import BRAND_PINK

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ImageTab(BaseTab):
    THUMB = 48

    def __init__(self, page: ft.Page, config):
        super().__init__(page, config)
        self._folder_dirs: list[Path] = []
        self._current_folder: Path | None = None
        self._images: list[Path] = []
        self._selected: set[Path] = set()
        self._checks: dict[Path, ft.Checkbox] = {}
        # (resolved_path_str, mtime_ns) -> PNG bytes
        self._thumb_cache: dict[tuple[str, int], bytes] = {}

        self.folder_hint = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.folder_list = ft.ListView(expand=True, spacing=2, padding=4)
        self.gallery_hint = ft.Text(
            "请选择左侧目录",
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            expand=True,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.gallery = ft.ListView(expand=True, spacing=2, padding=4)
        self.gallery_host = ft.Container(
            content=self.gallery,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            expand=True,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        )
        self.translate_btn = ft.FilledButton(
            "本地化选中图片",
            icon=ft.Icons.TRANSLATE,
            disabled=True,
            on_click=lambda e: self._confirm_translate(),
        )
        self.root.content = self.build()
        self.refresh_folders()

    def _rp(self) -> Path | None:
        p = Path(self.config.get("resource_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def _bp(self) -> Path | None:
        p = Path(self.config.get("behavior_pack_path").strip())
        return p if str(p) and p.is_dir() else None

    def _packs(self) -> list[tuple[str, Path]]:
        out = []
        rp, bp = self._rp(), self._bp()
        if rp:
            out.append(("资源包", rp))
        if bp:
            out.append(("行为包", bp))
        return out

    def build(self) -> ft.Control:
        folders_pane = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("图片目录", weight=ft.FontWeight.W_600, size=13, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.REFRESH,
                                tooltip="刷新目录",
                                on_click=lambda e: self.refresh_folders(),
                            ),
                        ],
                        spacing=0,
                    ),
                    self.folder_hint,
                    ft.Container(
                        content=self.folder_list,
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        expand=True,
                    ),
                ],
                spacing=6,
                expand=True,
            ),
            width=300,
        )

        # 普通 Row：hint 自带 expand，切勿 wrap=True + expand（会触发 Flutter ErrorWidget 灰块）
        gallery_pane = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        self.gallery_hint,
                        ft.TextButton("全选", on_click=lambda e: self._set_all(True)),
                        ft.TextButton("全不选", on_click=lambda e: self._set_all(False)),
                        self.translate_btn,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.gallery_host,
            ],
            spacing=8,
            expand=True,
        )

        body = ft.Column(
            controls=[
                ft.Text(
                    "左侧选目录，右侧勾选要本地化的图片（点整行也可切换）。"
                    "写回强制保持原分辨率；原图备份到同目录 _backup/。",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(
                    controls=[folders_pane, gallery_pane],
                    spacing=12,
                    expand=True,
                ),
                self.make_progress_row(),
            ],
            spacing=10,
            expand=True,
        )
        return ft.Column(
            controls=[body, self.make_log_panel()],
            spacing=12,
            expand=True,
        )

    def _rel_label(self, path: Path) -> str:
        for _, pack in self._packs():
            try:
                return f"{pack.name} / {path.relative_to(pack)}"
            except ValueError:
                continue
        return str(path)

    def _thumb_bytes(self, path: Path) -> bytes | None:
        """生成小缩略图 PNG 字节，按 path+mtime 内存缓存。"""
        try:
            key = (str(path.resolve()), path.stat().st_mtime_ns)
        except OSError:
            return None
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached
        try:
            from PIL import Image

            with Image.open(path) as im:
                im = im.convert("RGBA") if im.mode in ("P", "LA") else im
                im.thumbnail((self.THUMB, self.THUMB))
                buf = io.BytesIO()
                im.save(buf, format="PNG")
            data = buf.getvalue()
            self._thumb_cache[key] = data
            return data
        except Exception as e:
            self.log(f"  缩略图失败 {path.name}: {e}")
            return None

    def _is_likely_guidebook(self, folder: Path) -> bool:
        """路径含 book/guide，或目录内图片名含 page → 通常需本地化。"""
        for part in folder.parts:
            low = part.casefold()
            if "book" in low or "guide" in low:
                return True
        try:
            for p in folder.iterdir():
                if (
                    p.is_file()
                    and p.suffix.lower() in IMAGE_EXTENSIONS
                    and "page" in p.name.casefold()
                ):
                    return True
        except OSError:
            pass
        return False

    def _discover_image_dirs(self) -> list[Path]:
        found: dict[Path, int] = {}
        for _, pack in self._packs():
            for p in pack.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                if "_backup" in p.parts:
                    continue
                parent = p.parent
                found[parent] = found.get(parent, 0) + 1
        items = sorted(
            found.items(),
            key=lambda kv: (
                0 if self._is_likely_guidebook(kv[0]) else 1,
                len(kv[0].parts),
                str(kv[0]).casefold(),
            ),
        )
        return [p for p, _n in items[:120]]

    def _set_gallery(self, controls: list[ft.Control]) -> None:
        self.gallery.controls = controls
        try:
            self.gallery.update()
        except Exception:
            try:
                self.page.update()
            except Exception:
                pass

    def refresh_folders(self) -> None:
        self.folder_list.controls.clear()
        self._folder_dirs = self._discover_image_dirs()
        if not self._packs():
            self.folder_hint.value = "当前模组没有可用包"
            self.folder_list.controls.append(
                ft.Text("请先在首屏选择模组", color=ft.Colors.ON_SURFACE_VARIANT)
            )
        elif not self._folder_dirs:
            self.folder_hint.value = "未找到含图片的子目录"
            self.folder_list.controls.append(
                ft.Text("未找到图片目录", color=ft.Colors.ON_SURFACE_VARIANT)
            )
        else:
            pinned = sum(1 for d in self._folder_dirs if self._is_likely_guidebook(d))
            hint = f"共 {len(self._folder_dirs)} 个目录"
            if pinned:
                hint += f"（置顶建议本地化 {pinned} 个）"
            self.folder_hint.value = hint
            for d in self._folder_dirs:
                count = sum(
                    1
                    for p in d.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
                )
                likely = self._is_likely_guidebook(d)
                if likely:
                    tile = ft.ListTile(
                        leading=ft.Icon(ft.Icons.MENU_BOOK, color=BRAND_PINK, size=22),
                        title=ft.Text(
                            self._rel_label(d),
                            size=12,
                            color=BRAND_PINK,
                            weight=ft.FontWeight.W_600,
                        ),
                        subtitle=ft.Text(
                            f"建议本地化 · {count} 张",
                            size=11,
                            color=BRAND_PINK,
                        ),
                        on_click=lambda e, p=d: self.open_folder(p),
                    )
                else:
                    tile = ft.ListTile(
                        title=ft.Text(self._rel_label(d), size=12),
                        subtitle=ft.Text(f"{count} 张", size=11),
                        on_click=lambda e, p=d: self.open_folder(p),
                    )
                self.folder_list.controls.append(tile)
        if self._current_folder and self._current_folder in self._folder_dirs:
            self.open_folder(self._current_folder)
        else:
            self._current_folder = None
            self._images = []
            self._selected.clear()
            self.gallery_hint.value = "请选择左侧目录"
            self._set_gallery(
                [ft.Text("请选择左侧目录以预览图片", color=ft.Colors.ON_SURFACE_VARIANT, size=13)]
            )
            self._sync_translate_btn()
        try:
            self.folder_hint.update()
            self.folder_list.update()
            self.gallery_hint.update()
        except Exception:
            pass

    def _read_size_label(self, path: Path) -> str:
        try:
            from PIL import Image

            with Image.open(path) as im:
                return f"{im.size[0]}×{im.size[1]}"
        except Exception:
            return "?"

    def _make_row(self, path: Path) -> ft.Control:
        size_label = self._read_size_label(path)
        cb = ft.Checkbox(
            value=path in self._selected,
            on_change=lambda e, p=path: self._on_check(p, e.control.value),
        )
        self._checks[path] = cb
        thumb = self._thumb_bytes(path)
        if thumb:
            leading: ft.Control = ft.Image(
                src=thumb,
                width=self.THUMB,
                height=self.THUMB,
                fit=ft.BoxFit.CONTAIN,
                error_content=ft.Icon(
                    ft.Icons.BROKEN_IMAGE_OUTLINED,
                    size=24,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            )
        else:
            leading = ft.Icon(
                ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED,
                size=28,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        return ft.ListTile(
            leading=leading,
            title=ft.Text(path.name, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(size_label, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            trailing=cb,
            on_click=lambda e, p=path: self._toggle_row(p),
        )

    def _toggle_row(self, path: Path) -> None:
        checked = path not in self._selected
        self._on_check(path, checked)
        cb = self._checks.get(path)
        if cb is not None:
            cb.value = checked
            try:
                cb.update()
            except Exception:
                pass

    def open_folder(self, folder: Path) -> None:
        try:
            self._current_folder = folder
            self._images = sorted(
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
            self._selected = set(self._images)
            self._checks.clear()
            self.gallery_hint.value = f"{self._rel_label(folder)}  ·  {len(self._images)} 张"
            try:
                self.gallery_hint.update()
            except Exception:
                pass

            if not self._images:
                self._set_gallery(
                    [ft.Text("该目录下没有图片", color=ft.Colors.ON_SURFACE_VARIANT, size=13)]
                )
                self._sync_translate_btn()
                return

            self.log(f"预览目录：{self._rel_label(folder)}（{len(self._images)} 张）")
            rows: list[ft.Control] = []
            for path in self._images:
                try:
                    rows.append(self._make_row(path))
                except Exception as e:
                    self.log(f"  预览项失败 {path.name}: {e}")
                    rows.append(
                        ft.Text(f"无法预览: {path.name} ({e})", color=ft.Colors.ERROR, size=12)
                    )

            self._set_gallery(rows)
            self._sync_translate_btn()
            self.log(f"已加载预览 {len(rows)} 项")
        except Exception as e:
            self.log(f"打开目录失败: {e}")
            self._set_gallery(
                [ft.Text(f"打开目录失败: {e}", color=ft.Colors.ERROR, size=13)]
            )

    def _on_check(self, path: Path, checked: bool | None) -> None:
        if checked:
            self._selected.add(path)
        else:
            self._selected.discard(path)
        self._sync_translate_btn()

    def _set_all(self, checked: bool) -> None:
        self._selected = set(self._images) if checked else set()
        for path, cb in self._checks.items():
            cb.value = checked
            try:
                cb.update()
            except Exception:
                pass
        self._sync_translate_btn()

    def _sync_translate_btn(self) -> None:
        n = len(self._selected)
        self.translate_btn.disabled = n == 0
        self.translate_btn.text = f"本地化选中图片（{n}）"
        try:
            self.translate_btn.update()
        except Exception:
            pass

    def _confirm_translate(self) -> None:
        if not self.config.get("image_llm", "api_key"):
            error_toast(self.page, "请先在设置中填写图片翻译 API Key")
            return
        images = [p for p in self._images if p in self._selected]
        if not images:
            error_toast(self.page, "请先勾选要本地化的图片")
            return
        confirm(
            self.page,
            title="确认图片本地化",
            message=f"将本地化选中的 {len(images)} 张图片，并强制保持各自原分辨率。原图备份到 _backup/。",
            on_yes=lambda: self.run_in_thread(self._images_worker, images),
        )

    def _images_worker(self, images: list[Path]) -> None:
        total = len(images)
        code = (self.config.get("target_language") or DEFAULT_CODE).strip() or DEFAULT_CODE
        lang = label_of(code)
        self.log("=" * 50)
        self.log(f"图片本地化（→ {lang}）：选中 {total} 张（保持原分辨率）")
        ok = 0
        for n, path in enumerate(images, 1):
            if self._stop_flag.is_set():
                self.log("已停止")
                break
            self.log(f"[{n}/{total}] {path.name}")
            if translate_image_file(
                path, self.config.get("image_llm"), True, self.log, lang_label=lang
            ):
                ok += 1
            self.set_progress(n, total)
        self.log(f"图片本地化结束：成功 {ok}/{total}")
        if self._current_folder is not None:
            try:
                self.open_folder(self._current_folder)
            except Exception:
                pass
        toast(self.page, f"图片本地化完成：成功 {ok}/{total}")
