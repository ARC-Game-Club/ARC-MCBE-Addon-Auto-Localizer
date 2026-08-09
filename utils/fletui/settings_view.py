# -*- coding: utf-8 -*-
"""设置页：署名与 LLM 接口配置。"""
from __future__ import annotations

import flet as ft

from ..llm_service import make_client
from .base_tab import BaseTab
from .components import SectionCard, error_toast, toast


class SettingsView(BaseTab):
    def __init__(self, page: ft.Page, config, on_saved=None):
        super().__init__(page, config)
        self.on_saved = on_saved
        self.credit_field = ft.TextField(
            label="默认汉化者名称",
            value=(config.get("translator_credit") or "DEVILENMO").strip() or "DEVILENMO",
            hint_text="包名后显示为 （名称汉化），默认 DEVILENMO",
        )
        self.text_base = ft.TextField(label="Base URL", value=config.get("text_llm", "base_url"), expand=True)
        self.text_key = ft.TextField(label="API Key", value=config.get("text_llm", "api_key"), password=True, can_reveal_password=True, expand=True)
        self.text_model = ft.TextField(label="Model", value=config.get("text_llm", "model"), expand=True)
        self.text_proxy = ft.TextField(label="代理（留空=不使用）", value=config.get("text_llm", "proxy"), expand=True)

        self.img_base = ft.TextField(label="Base URL", value=config.get("image_llm", "base_url"), expand=True)
        self.img_key = ft.TextField(label="API Key", value=config.get("image_llm", "api_key"), password=True, can_reveal_password=True, expand=True)
        self.img_model = ft.TextField(label="Model", value=config.get("image_llm", "model"), expand=True)
        self.img_proxy = ft.TextField(label="代理（留空=不使用）", value=config.get("image_llm", "proxy"), expand=True)
        self.root.content = self.build()

    def build(self) -> ft.Control:
        body = ft.Column(
            controls=[
                ft.Text("配置默认汉化者与 AI 接口，改完点击「保存配置」生效。", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                SectionCard("汉化者署名", self.credit_field),
                SectionCard(
                    "文本翻译 LLM（用于 .lang / display_name 汉化）",
                    self.text_base,
                    self.text_key,
                    self.text_model,
                    self.text_proxy,
                ),
                SectionCard(
                    "图片翻译 LLM（用于图片汉化，需支持图像输入 + 图像输出）",
                    self.img_base,
                    self.img_key,
                    self.img_model,
                    self.img_proxy,
                ),
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

    def _gather(self) -> None:
        credit = (self.credit_field.value or "").strip() or "DEVILENMO"
        self.credit_field.value = credit
        self.config.set(credit, "translator_credit")
        self.config.set((self.text_base.value or "").strip(), "text_llm", "base_url")
        self.config.set((self.text_key.value or "").strip(), "text_llm", "api_key")
        self.config.set((self.text_model.value or "").strip(), "text_llm", "model")
        self.config.set((self.text_proxy.value or "").strip(), "text_llm", "proxy")
        self.config.set((self.img_base.value or "").strip(), "image_llm", "base_url")
        self.config.set((self.img_key.value or "").strip(), "image_llm", "api_key")
        self.config.set((self.img_model.value or "").strip(), "image_llm", "model")
        self.config.set((self.img_proxy.value or "").strip(), "image_llm", "proxy")

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
