# -*- coding: utf-8 -*-
"""设置页：目标语言、署名、LLM 与网盘插件。"""
from __future__ import annotations

import webbrowser

import flet as ft

from ..cloud_drives import CloudDrive, CloudDriveError, drivers_from
from ..languages import DEFAULT_CODE, LANGUAGES, credit_suffix
from ..llm_service import make_client
from ..paths import get_minecraft_base_dir
from .base_tab import BaseTab
from .components import SectionCard, error_toast, toast


class _DrivePanel:
    def __init__(self, view: "SettingsView", drive: CloudDrive):
        self.view = view
        self.drive = drive
        self.enabled = ft.Switch(label="导出后自动上传", value=drive.is_enabled())
        self.fields: dict[str, ft.TextField] = {}
        for spec in drive.config_fields():
            self.fields[spec.key] = ft.TextField(
                label=spec.label,
                value=str(drive.cfg.get(spec.key) or ""),
                password=spec.kind == "password",
                can_reveal_password=spec.kind == "password",
                hint_text=spec.hint or None,
            )
        self.status = ft.Text(drive.status_text(), size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.code = None
        if drive.auth_mode == "oauth_code":
            self.code = ft.TextField(label="授权码", hint_text="浏览器授权后粘贴这里的 code")

    def controls(self) -> list[ft.Control]:
        items: list[ft.Control] = [
            ft.Text(self.drive.notes, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            self.enabled,
            *self.fields.values(),
            self.status,
        ]
        if self.code is not None:
            items.append(self.code)
        buttons = []
        if self.drive.auth_mode == "oauth_code":
            buttons.append(
                ft.OutlinedButton("打开授权页", icon=ft.Icons.OPEN_IN_BROWSER, on_click=lambda e: self._open_auth())
            )
            buttons.append(
                ft.OutlinedButton("完成授权", icon=ft.Icons.VERIFIED_USER, on_click=lambda e: self._finish_auth())
            )
        elif self.drive.auth_mode == "cookie":
            buttons.append(
                ft.OutlinedButton("打开网盘网页", icon=ft.Icons.OPEN_IN_BROWSER, on_click=lambda e: self._open_auth())
            )
        buttons.append(ft.OutlinedButton("测试网盘", icon=ft.Icons.CLOUD, on_click=lambda e: self._test()))
        items.append(ft.Row(controls=buttons, spacing=10, wrap=True))
        return items

    def gather(self) -> None:
        self.drive.cfg["enabled"] = bool(self.enabled.value)
        for key, field in self.fields.items():
            self.drive.cfg[key] = (field.value or "").strip()

    def refresh_status(self) -> None:
        self.status.value = self.drive.status_text()
        try:
            self.status.update()
        except Exception:
            pass

    def _open_auth(self) -> None:
        self.view._gather()
        try:
            url = self.drive.authorize_url()
        except CloudDriveError as err:
            error_toast(self.view.page, str(err))
            return
        webbrowser.open(url)
        if self.drive.auth_mode == "oauth_code":
            self.view.log(f"已打开{self.drive.display_name}授权页。同意后把 code 粘回来，再点「完成授权」。")
            self.view.log("若提示 redirect_uri 不匹配：开放平台安全设置里回调地址填 oob。")
        else:
            self.view.log(f"已打开{self.drive.display_name}。登录后 F12 → Network 复制 Cookie，粘到设置里保存。")
        toast(self.view.page, f"已打开{self.drive.display_name}")

    def _finish_auth(self) -> None:
        self.view._gather()
        code = (self.code.value or "").strip() if self.code else ""
        if not code:
            error_toast(self.view.page, "请先粘贴授权码")
            return
        self.view.run_in_thread(self._finish_worker, code)

    def _finish_worker(self, code: str) -> None:
        self.view.log(f"正在授权{self.drive.display_name} …")
        try:
            self.drive.exchange_code(code)
            name = self.drive.test_connection()
            self.view.config.save()
            self.view.log(f"✓ {self.drive.display_name}已授权：{name}")
            if self.code is not None:
                self.code.value = ""
                try:
                    self.code.update()
                except Exception:
                    pass
            self.refresh_status()
            toast(self.view.page, f"{self.drive.display_name}授权成功")
        except CloudDriveError as err:
            self.view.log(f"✗ {self.drive.display_name}授权失败: {err}")
            error_toast(self.view.page, str(err))

    def _test(self) -> None:
        self.view._gather()
        self.view.config.save()
        if not self.drive.is_authorized():
            error_toast(self.view.page, f"请先完成{self.drive.display_name}登录")
            return
        self.view.run_in_thread(self._test_worker)

    def _test_worker(self) -> None:
        self.view.log(f"测试{self.drive.display_name} …")
        try:
            name = self.drive.test_connection()
            self.view.config.save()
            self.view.log(f"✓ {self.drive.display_name}账号: {name}")
            self.refresh_status()
            toast(self.view.page, f"{self.drive.display_name}可用：{name}")
        except CloudDriveError as err:
            self.view.log(f"✗ {self.drive.display_name}测试失败: {err}")
            error_toast(self.view.page, str(err))


class SettingsView(BaseTab):
    def __init__(self, page: ft.Page, config, on_saved=None, file_picker: ft.FilePicker | None = None):
        super().__init__(page, config)
        self.on_saved = on_saved
        self.file_picker = file_picker
        current_code = (config.get("target_language") or DEFAULT_CODE).strip() or DEFAULT_CODE
        self.lang_dropdown = ft.Dropdown(
            label="目标语言",
            value=current_code,
            options=[
                ft.DropdownOption(key=lang.code, text=f"{lang.label}（{lang.code}）")
                for lang in LANGUAGES
            ],
            hint_text="LLM 将把文本翻译到所选语言；语言文件名为对应 .lang",
            expand=True,
        )
        credit = (config.get("translator_credit") or "DEVILENMO").strip() or "DEVILENMO"
        self.credit_field = ft.TextField(
            label="默认本地化者名称",
            value=credit,
            hint_text=f"包名后显示为 {credit_suffix(current_code, '名称')}，默认 DEVILENMO",
        )
        default_mods = str(get_minecraft_base_dir())
        self.mods_base_field = ft.TextField(
            label="模组根目录（留空=默认）",
            value=str(config.get("mods_base_dir") or ""),
            hint_text=default_mods,
            expand=True,
        )
        self.mods_base_hint = ft.Text(
            "应指向含 resource_packs / behavior_packs / development_* 的目录"
            f"（默认：{default_mods}）",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self.text_base = ft.TextField(label="Base URL", value=config.get("text_llm", "base_url"), expand=True)
        self.text_key = ft.TextField(label="API Key", value=config.get("text_llm", "api_key"), password=True, can_reveal_password=True, expand=True)
        self.text_model = ft.TextField(label="Model", value=config.get("text_llm", "model"), expand=True)
        self.text_proxy = ft.TextField(label="代理（留空=不使用）", value=config.get("text_llm", "proxy"), expand=True)

        self.img_base = ft.TextField(label="Base URL", value=config.get("image_llm", "base_url"), expand=True)
        self.img_key = ft.TextField(label="API Key", value=config.get("image_llm", "api_key"), password=True, can_reveal_password=True, expand=True)
        self.img_model = ft.TextField(label="Model", value=config.get("image_llm", "model"), expand=True)
        self.img_proxy = ft.TextField(label="代理（留空=不使用）", value=config.get("image_llm", "proxy"), expand=True)

        self.drive_panels = [_DrivePanel(self, drive) for drive in drivers_from(config._data)]
        self.root.content = self.build()

    def build(self) -> ft.Control:
        drive_cards = [
            SectionCard(f"{panel.drive.display_name}（导出后上传 / 分享）", *panel.controls())
            for panel in self.drive_panels
        ]
        body = ft.Column(
            controls=[
                ft.Text(
                    "配置目标语言、本地化者与 AI 接口，改完点击「保存配置」生效。",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                SectionCard(
                    "模组扫描目录",
                    self.mods_base_hint,
                    ft.Row(
                        controls=[
                            self.mods_base_field,
                            ft.OutlinedButton(
                                "浏览…",
                                icon=ft.Icons.FOLDER_OPEN,
                                on_click=self._browse_mods_base,
                            ),
                            ft.TextButton(
                                "恢复默认",
                                on_click=lambda e: self._clear_mods_base(),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                SectionCard("本地化目标语言", self.lang_dropdown),
                SectionCard("本地化者署名", self.credit_field),
                SectionCard(
                    "文本翻译 LLM（用于 .lang / display_name / 脚本本地化）",
                    self.text_base,
                    self.text_key,
                    self.text_model,
                    self.text_proxy,
                ),
                SectionCard(
                    "图片翻译 LLM（用于图片本地化，需支持图像输入 + 图像输出）",
                    self.img_base,
                    self.img_key,
                    self.img_model,
                    self.img_proxy,
                ),
                *drive_cards,
                ft.Row(
                    controls=[
                        ft.OutlinedButton("测试文本连接", icon=ft.Icons.WIFI_TETHERING, on_click=lambda e: self._test("text")),
                        ft.OutlinedButton("测试图片连接", icon=ft.Icons.WIFI_TETHERING, on_click=lambda e: self._test("image")),
                        ft.FilledButton("保存配置", icon=ft.Icons.SAVE, on_click=lambda e: self._save()),
                    ],
                    spacing=10,
                    wrap=True,
                ),
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        return ft.Column(
            controls=[body, self.make_log_panel()],
            spacing=12,
            expand=True,
        )

    def _clear_mods_base(self) -> None:
        self.mods_base_field.value = ""
        try:
            self.mods_base_field.update()
        except Exception:
            pass

    async def _browse_mods_base(self, e) -> None:
        if self.file_picker is None:
            error_toast(self.page, "当前环境无法打开文件夹选择器")
            return
        initial = (self.mods_base_field.value or "").strip() or str(get_minecraft_base_dir())
        path = await self.file_picker.get_directory_path(
            dialog_title="选择模组根目录（com.mojang 或同等结构）",
            initial_directory=initial,
        )
        if path:
            self.mods_base_field.value = path
            self.mods_base_field.update()

    def _gather(self) -> None:
        credit = (self.credit_field.value or "").strip() or "DEVILENMO"
        self.credit_field.value = credit
        code = (self.lang_dropdown.value or DEFAULT_CODE).strip() or DEFAULT_CODE
        self.config.set(code, "target_language")
        self.config.set(credit, "translator_credit")
        self.config.set((self.mods_base_field.value or "").strip(), "mods_base_dir")
        self.config.set((self.text_base.value or "").strip(), "text_llm", "base_url")
        self.config.set((self.text_key.value or "").strip(), "text_llm", "api_key")
        self.config.set((self.text_model.value or "").strip(), "text_llm", "model")
        self.config.set((self.text_proxy.value or "").strip(), "text_llm", "proxy")
        self.config.set((self.img_base.value or "").strip(), "image_llm", "base_url")
        self.config.set((self.img_key.value or "").strip(), "image_llm", "api_key")
        self.config.set((self.img_model.value or "").strip(), "image_llm", "model")
        self.config.set((self.img_proxy.value or "").strip(), "image_llm", "proxy")
        for panel in self.drive_panels:
            panel.gather()

    def _save(self) -> None:
        self._gather()
        if self.config.save():
            self.log(f"配置已保存到 {self.config.path}")
            toast(self.page, f"配置已保存到：{self.config.path}")
            if self.on_saved:
                self.on_saved()
        else:
            error_toast(self.page, "保存配置失败")

    def _test(self, kind: str) -> None:
        self._gather()
        if kind == "text":
            llm = self.config.get("text_llm")
            label = "文本"
        else:
            llm = self.config.get("image_llm")
            label = "图片"
        if not llm.get("api_key"):
            error_toast(self.page, f"请先填写{label}翻译 API Key")
            return
        self.run_in_thread(self._test_worker, llm, label)

    def _test_worker(self, llm, label) -> None:
        proxy = (llm.get("proxy") or "").strip()
        via = f"，代理 {proxy}" if proxy else "，直连"
        self.log(f"测试{label} LLM 连接{via} ...")
        try:
            client = make_client(llm)
            resp = client.chat.completions.create(
                model=llm.get("model"),
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            content = resp.choices[0].message.content or ""
            self.log(f"✓ {label} LLM 连接成功，响应: {content[:60]}")
        except Exception as e:
            self.log(f"✗ {label} LLM 连接失败: {e}")
