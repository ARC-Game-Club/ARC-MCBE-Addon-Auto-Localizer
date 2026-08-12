<div align="center">

# 弧光我的世界基岩 Addon 自动本地化器

# ARC MCBE Addon Auto Localizer

[![Codacy Grade](https://app.codacy.com/project/badge/Grade/077e44f1b31948caa7f55e909507df1e)](https://app.codacy.com/gh/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![Version](https://img.shields.io/badge/version-v1.1.0-blue)](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)
[![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flet](https://img.shields.io/badge/Flet-0.86-black)](https://flet.dev/)
[![License](https://img.shields.io/github/license/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/stargazers)

</div>

## 概述

## Overview

[ARC Minecraft](https://github.com/ARC-Minecraft) 出品的 Minecraft 基岩版（MCBE）Addon / 模组桌面本地化工具。

A desktop localizer for Minecraft Bedrock (MCBE) addons / mods from [ARC Minecraft](https://github.com/ARC-Minecraft).

自动扫描并配对资源包与行为包，借助 LLM 将语言文件、Display Name、脚本提示与图片文字翻译到**任意目标语言**（简体中文、日语、德语、法语、西班牙语等），并提供灵动视效、成就兼容、实体工具、本地化包导出与网盘上传。

It scans and pairs resource / behavior packs, uses an LLM to translate language files, display names, script tips, and image text into **any target language** (Simplified Chinese, Japanese, German, French, Spanish, and more), and also provides PBR, achievement compatibility, entity tools, pack export, and cloud-drive upload.

仓库：[`ARC-MCBE-Addon-Auto-Localizer`](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)

Repo: [`ARC-MCBE-Addon-Auto-Localizer`](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)

产品短名：**弧光自动本地化工具**

Short name: **ARC Auto Localizer**

## 作者信息

## Author

- **作者**: [DEVILENMO](https://github.com/DEVILENMO)
- **Author**: [DEVILENMO](https://github.com/DEVILENMO)
- **B 站**: [https://space.bilibili.com/37202522](https://space.bilibili.com/37202522)
- **Bilibili**: [https://space.bilibili.com/37202522](https://space.bilibili.com/37202522)
- **邮箱**: DEVILENMO@gmail.com
- **Email**: DEVILENMO@gmail.com
- **组织**: [ARC Minecraft](https://github.com/ARC-Minecraft) / ARCStudio
- **Org**: [ARC Minecraft](https://github.com/ARC-Minecraft) / ARCStudio
- **版本**: 1.1.0
- **Version**: 1.1.0
- **推荐 Python 版本**: 3.12+
- **Recommended Python**: 3.12+
- **UI 框架**: Flet 0.86
- **UI framework**: Flet 0.86

---

## 快速开始（普通用户）

## Quick start (end users)

1. 打开 [Releases](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/releases) 下载最新 `exe`
1. Open [Releases](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/releases) and download the latest `exe`
2. 双击运行（Windows，无需安装 Python）
2. Double-click to run (Windows; Python is not required)
3. 右上角「设置」选择**本地化目标语言**，并填写文本 / 图片 LLM 的 Base URL、API Key（及可选代理）
3. Open **Settings** (top right), pick the **target language**, and fill in text / image LLM Base URL, API Key, and optional proxy
4. 在首屏选择要处理的模组，进入工具箱按步骤操作
4. On the home screen, select an addon and follow the toolbox steps

本机需已安装 Minecraft Bedrock，工具会读取：

Minecraft Bedrock must be installed locally. The tool reads:

```
%APPDATA%\Minecraft Bedrock\Users\Shared\games\com.mojang\
  ├── resource_packs /
  ├── behavior_packs /
  ├── development_resource_packs /
  └── development_behavior_packs /
```

用户配置（含 API Key，**不会**进仓库）：

User config (including API keys, **not** committed to the repo):

```
%APPDATA%\ARCStudio\弧光自动本地化工具\config.json
```

从旧版「弧光自动汉化工具」升级时，会自动迁移 AppData 下的旧配置。

Upgrading from the old “ARC Auto Chinese Localizer” automatically migrates the previous AppData config.

---

## 本地化目标语言

## Target language

在「设置 → 本地化目标语言」下拉框选择 MCBE 官方支持的语言码（共 29 种），例如：

In **Settings → Target language**, pick one of the 29 official MCBE language codes, for example:

| 代码 / Code | 名称 / Name | 署名后缀示例 / Credit suffix |
|------|------|--------------|
| `zh_CN` | 简体中文<br>Simplified Chinese | `（xxx汉化）` |
| `zh_TW` | 繁體中文<br>Traditional Chinese | `（xxx漢化）` |
| `ja_JP` | 日语<br>Japanese | `（xxx翻訳）` |
| `ko_KR` | 韩语<br>Korean | `(xxx 번역)` |
| `de_DE` / `fr_FR` / `es_ES` / … | 德语 / 法语 / 西班牙语等<br>German / French / Spanish, etc. | `(xxx Localization)` |
| `en_US` / `en_GB` | 英语<br>English | `(xxx Localization)` |

效果：

Effects:

- 语言文件生成为 `{语言码}.lang`，并写入 `languages.json`
- Language files are written as `{code}.lang` and listed in `languages.json`
- LLM 提示词中的目标语言名随选择变化
- The target language name in LLM prompts follows the selection
- 包名署名后缀按语言使用上表模板
- Pack-name credit suffixes use the templates above
- 重命名文件夹、导出文件名优先读取目标语言 `pack.name`
- Folder rename and export filenames prefer the target-language `pack.name`

---

## 功能介绍

## Features

### 首屏：模组选择

### Home: addon picker

- 扫描本地资源包 / 行为包，按 `manifest` UUID 依赖自动配对
- Scan local resource / behavior packs and pair them by `manifest` UUID dependencies
- 卡片展示 RP / BP 徽章与包名
- Cards show RP / BP badges and pack names
- 支持按目标语言 `pack.name` 等规则预览并整理模组文件夹名称
- Preview and rename addon folders using the target-language `pack.name` and related rules

### ① 模组本地化

### ① Addon localization

进入本页后会自动规范化 JSON / JS（内容无变化则跳过写盘）。

Entering this page auto-formats JSON / JS (unchanged files are not rewritten).

| 步骤 / Step | 说明 / Description |
|------|------|
| Display Name 标准化<br>Display Name normalization | 扫描 JSON 中的 `minecraft:display_name`：能解析出 `minecraft:item` / `entity` / `block` + `identifier` 时，把 value 改成 `item.ns:id.name` / `entity.ns:id.name` / `tile.ns:id.name`，并把英文原文写入 `en_US.lang` 与目标语言 `.lang`；无法推导的条目回退为 LLM 直译写回 value<br>Scan `minecraft:display_name` in JSON. When `minecraft:item` / `entity` / `block` plus `identifier` can be resolved, rewrite the value to `item.ns:id.name` / `entity.ns:id.name` / `tile.ns:id.name`, and append the English source to `en_US.lang` and the target `.lang`. Entries that cannot be derived fall back to LLM in-place translation. |
| 语言文件翻译<br>Language-file translation | 确保目标语言在 `languages.json`、从英文 lang 复制并调用 LLM 批量翻译条目（与 `en_US` 相同的条目视为未译）<br>Ensure the target language is in `languages.json`, copy from the English lang file, and batch-translate with the LLM (entries still identical to `en_US` are treated as untranslated). |
| 脚本提示本地化<br>Script-tip localization | 本地化 `sendMessage` / `form.title\|button\|label\|body\|toggle\|…`、`setActionBar`、`tooltip` 等玩家可见字符串；跳过语言键与含 `.map/.join` 的复杂多行模板；写入前 `node --check` 校验，失败自动回退<br>Localize player-visible strings such as `sendMessage`, form `title\|button\|label\|body\|toggle\|…`, `setActionBar`, and `tooltip`. Skip lang keys and complex multiline templates with `.map/.join`. Validate with `node --check` before write; roll back on failure. |
| 本地化者署名<br>Localizer credit | 在包名后追加按语言变化的署名后缀，默认 DEVILENMO，可在设置中改<br>Append a language-specific credit suffix to the pack name. Default is DEVILENMO; changeable in Settings. |
| 一键本地化<br>One-click localize | 按顺序执行：标准化 → 语言 → 脚本 → 署名<br>Runs in order: normalize → language files → scripts → credit |

### ② 图片本地化

### ② Image localization

独立页面：左侧列出模组内含图目录，右侧缩略图预览并勾选；只处理选中文件。

Dedicated page: folders with images on the left, thumbnail preview and checkboxes on the right; only checked files are processed.

- 写回时**强制保持原图像素宽高**（含异形比例）；模型输出尺寸不一致时会自动缩放回原分辨率
- Writes back at the **original pixel size** (including non-square ratios); model output is scaled back if the size differs
- 原图备份到同目录 `_backup/`
- Originals are backed up to `_backup/` in the same folder
- 路径含 `book` / `guide`，或目录内图片名含 `page` 的目录会**置顶**并以醒目颜色标注「建议本地化」（guidebook 类贴图）
- Folders whose path contains `book` / `guide`, or whose image names contain `page`, are **pinned** and highlighted as “suggested” (guidebook-style textures)
- 需在设置中配置支持图像输入/输出的图片 LLM
- Configure an image LLM that supports image input and output in Settings

### ③ 灵动视效

### ③ Vibrant Visuals (PBR)

- 检测资源包 `manifest.json` 的 `capabilities` 是否包含 `pbr`
- Check whether the resource pack `manifest.json` `capabilities` include `pbr`
- 一键添加 / 移除灵动视效（PBR）支持，并备份原 manifest
- One-click add / remove PBR support, with a backup of the original manifest

### ④ 成就兼容

### ④ Achievement compatibility

- 检测资源包 / 行为包是否声明：
- Check whether resource / behavior packs declare:

```json
"metadata": {
    "product_type": "addon"
}
```

- 一键为当前模组各包写入或移除该字段（保留 `authors` 等其它 metadata），使模组以附加包方式加载并保持成就可用
- One-click write or remove this field on each pack of the current addon (other metadata such as `authors` is kept), so the addon loads as an addon and achievements stay available

### ⑤ 实体工具

### ⑤ Entity tools

- 扫描行为包实体相关数据（如血量等），结果在界面文本框中展示，便于复制
- Scan behavior-pack entity data (e.g. health) and show it in a text box for easy copy

### ⑥ 导出本地化包

### ⑥ Export localized pack

- 将当前选中模组打包导出为可分发的压缩包（包内容位于压缩包根目录，含 `manifest.json`）
- Export the selected addon as a distributable archive (pack contents at the zip root, including `manifest.json`)
- 可勾选网盘开关，导出后自动上传 / 分享
- Optionally enable cloud drives to upload / share after export

### 网盘上传与分享

### Cloud-drive upload and sharing

导出页可将成品 `.mcaddon` / `.mcpack` 上传到网盘（**不是**用来下载模组）。

The export page can upload the finished `.mcaddon` / `.mcpack` to a cloud drive (**not** for downloading addons).

驱动以插件方式注册在 `utils/cloud_drives/`，设置页与导出页会按注册表自动出现。

Drivers register as plugins under `utils/cloud_drives/`; Settings and Export pick them up automatically from the registry.

| 网盘 / Drive | 登录方式 / Auth | 自动分享 / Auto share | 说明 / Notes |
|------|----------|----------|------|
| 百度网盘<br>Baidu Netdisk | OAuth 授权码（需自建开放平台应用，回调填 `oob`）<br>OAuth auth code (create your own Open Platform app; redirect URI `oob`) | 否（个人应用限制）<br>No (personal-app limit) | 分片上传到 `/apps/<应用名>/`<br>Chunked upload to `/apps/<app name>/` |
| 夸克网盘<br>Quark | 网页 Cookie<br>Web cookie | 是（可设提取码）<br>Yes (optional password) | 上传后自动创建分享链接<br>Creates a share link after upload |

设置里可为每家网盘开关「导出后自动上传」，并测试连接；导出页也可临时勾选本次要上传的网盘。

In Settings you can toggle “auto-upload after export” per drive and test the connection; the Export page can also temporarily choose which drives to use for this export.

### 设置

### Settings

- 本地化目标语言（下拉）
- Target language (dropdown)
- 默认本地化者名称
- Default localizer name
- 文本 LLM / 图片 LLM：Base URL、API Key、模型名、代理
- Text LLM / image LLM: Base URL, API Key, model, proxy
- 网盘插件配置与授权
- Cloud-drive plugin config and auth
- 连接测试与保存
- Connection test and save

### 其它

### Other

- 底部运行日志，支持一键复制全部日志
- Run log at the bottom, with one-click copy of all logs
- 各耗时任务在后台线程执行，界面保持可响应
- Long tasks run on background threads so the UI stays responsive

---

## 开发者运行

## Run from source

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
.\.venv\Scripts\python.exe mcbe_localization_hub.py
```

推荐 **Python 3.12+**。首次启动 Flet 桌面客户端时可能需要下载运行时；网络不通时可配置系统 / 环境代理后重试。

**Python 3.12+** is recommended. The first Flet desktop launch may download a runtime; if the network fails, configure a system / env proxy and retry.

## 打包

## Packaging

```bash
flet pack mcbe_localization_hub.py -n mcbe_localization_hub ^
  -i assets\app_icon.ico --add-data "assets;assets" ^
  --product-name "弧光自动本地化工具" --company-name "ARCStudio" ^
  --product-version "1.1.0" --file-version "1.1.0" ^
  --hidden-import openai --hidden-import httpx -y
```

请使用项目 `.venv`（勿用臃肿的全局 conda 环境），产物在 `dist/`（已 gitignore）。正式版通过 GitHub Release 发布可双击运行的 `exe`。

Use the project `.venv` (not a bloated global conda env). Output is in `dist/` (gitignored). Official builds ship a double-clickable `exe` via GitHub Releases.

## 目录说明

## Layout

| 路径 / Path | 说明 / Description |
|------|------|
| `mcbe_localization_hub.py` | 启动入口（Flet）<br>Flet entry point |
| `VERSION` | 当前版本号<br>Current version |
| `utils/` | 业务逻辑<br>Business logic |
| `utils/languages.py` | 目标语言码、署名后缀模板<br>Target language codes and credit-suffix templates |
| `utils/cloud_drives/` | 网盘插件（百度 / 夸克）<br>Cloud-drive plugins (Baidu / Quark) |
| `utils/fletui/` | Flet 界面<br>Flet UI |
| `assets/` | 图标等资源<br>Icons and assets |
| `ui/` | 格式化等被 service 复用的辅助模块<br>Helpers reused by services (formatting, etc.) |
| `requirements.txt` | 依赖锁定<br>Pinned dependencies |
| `LICENSE` | MIT |
| `.venv/` | 本地虚拟环境（不上传）<br>Local venv (not uploaded) |

## 版本

## Version

当前版本：**1.1.0**

Current version: **1.1.0**

### 更新说明

### Changelog

#### v1.1.0

- **多语言本地化**：设置中可选目标语言（MCBE 官方 29 种语言码）；语言文件、LLM 提示词、包名署名后缀随语言变化
- **Multi-language localization**: pick a target language in Settings (29 official MCBE codes); language files, LLM prompts, and pack credit suffixes follow the selection
- **Display Name 标准化**：将 `minecraft:display_name` 写成 `item./entity./tile.` 语言键并落地 `.lang`，再由语言文件步骤统一翻译；无法推导的条目回退直译
- **Display Name normalization**: rewrite `minecraft:display_name` to `item./entity./tile.` lang keys, write them into `.lang`, then translate via the language-file step; underivable entries fall back to in-place translation
- **网盘上传**：导出后可上传到百度网盘（OAuth）/ 夸克网盘（Cookie，支持自动分享）
- **Cloud-drive upload**: after export, upload to Baidu Netdisk (OAuth) / Quark (cookie, auto share)
- **产品更名**：弧光自动本地化工具；旧版 AppData 配置自动迁移
- **Rename**: ARC Auto Localizer; legacy AppData config is migrated automatically

#### v1.0.3

- **窗口图标**：打包后从 `sys._MEIPASS/assets` 正确加载 `app_icon.ico`，标题栏不再显示 Flet 默认鱼标
- **Window icon**: frozen builds load `app_icon.ico` from `sys._MEIPASS/assets`; the title bar no longer shows the default Flet fish icon

#### v1.0.2

- **图片汉化预览修复**：修复工具栏 `Row(wrap=True)` 与 `expand` 冲突导致右侧整片灰屏（Flutter ErrorWidget）的问题；预览改为「缩略图 + 文件名 + 分辨率 + 勾选」列表
- **Image preview fix**: fixed grey screen (Flutter ErrorWidget) from toolbar `Row(wrap=True)` vs `expand`; preview is now thumbnail + name + resolution + checkbox
- **改名后路径同步**：语言/署名后按中文包名重命名文件夹时，可靠回写 `resource_pack_path` / `behavior_pack_path`，并刷新状态栏与图片目录，避免后续功能报路径不存在
- **Path sync after rename**: after renaming folders by localized pack name, reliably rewrite `resource_pack_path` / `behavior_pack_path` and refresh the status bar and image folders
- **图片目录体验**：长路径自适应多行显示；含 `book`/`guide` 或图片名含 `page` 的目录置顶并以品牌色标注「建议汉化」
- **Image folder UX**: long paths wrap; folders with `book`/`guide` or image names containing `page` are pinned and highlighted

#### v1.0.1

- **图片汉化独立页**：侧栏新增「图片汉化」；按目录预览缩略图，勾选后汉化，不再整目录一键硬翻
- **Dedicated image page**: sidebar “Image localization”; preview thumbnails by folder and localize only checked files
- **保持原分辨率**：汉化写回强制对齐原图像素宽高（含异形比例）；模型尺寸不一致时自动最近邻缩回
- **Keep original resolution**: write-back matches original pixel size (including odd ratios); nearest-neighbor scale if the model size differs
- **脚本提示**：支持 `.toggle` / `tooltip` 等表单文案；允许 `${Math.floor(...)}` 等简单函数插值；跳过含 `.map/.join` 的复杂多行模板，避免脚本语法被截断
- **Script tips**: support `.toggle` / `tooltip` and similar form text; allow simple interpolations like `${Math.floor(...)}`; skip complex multiline templates with `.map/.join`
- **成就兼容**：可为 RP/BP 写入或移除 `metadata.product_type = "addon"`
- **Achievement compatibility**: write or remove `metadata.product_type = "addon"` on RP/BP
- **体验**：格式化与汉化步骤串行，避免日志交错；运行日志支持一键复制；JS 内容无变化时跳过写盘
- **UX**: format and localize steps run serially to avoid interleaved logs; one-click copy of run logs; skip rewriting unchanged JS

#### v1.0.0

- 首个正式版：模组配对、语言 / Display Name / 脚本 / 署名、灵动视效、实体工具、导出汉化包与 Windows 一键 exe
- First stable release: addon pairing, language / Display Name / script / credit, PBR, entity tools, pack export, and a one-click Windows exe

## 许可与归属

## License

本项目采用 [MIT License](LICENSE)。

This project is released under the [MIT License](LICENSE).

主要作者 **DEVILENMO**（[B 站主页](https://space.bilibili.com/37202522)），归属 [ARC Minecraft](https://github.com/ARC-Minecraft) / ARCStudio。Issues 与反馈请到本仓库提出。

Lead author **DEVILENMO** ([Bilibili](https://space.bilibili.com/37202522)), under [ARC Minecraft](https://github.com/ARC-Minecraft) / ARCStudio. Please file issues and feedback in this repository.
