<div align="center">

# ARC MCBE Addon Auto Localizer / 弧光我的世界基岩 Addon 自动汉化器

[![Codacy Grade](https://app.codacy.com/project/badge/Grade/077e44f1b31948caa7f55e909507df1e)](https://app.codacy.com/gh/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![Version](https://img.shields.io/badge/version-v1.0.3-blue)](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)
[![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flet](https://img.shields.io/badge/Flet-0.86-black)](https://flet.dev/)
[![License](https://img.shields.io/github/license/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/stargazers)

</div>

## 概述

[ARC Minecraft](https://github.com/ARC-Minecraft) 出品的 Minecraft 基岩版（MCBE）Addon / 模组桌面汉化工具。自动扫描并配对资源包与行为包，借助 LLM 翻译语言文件、Display Name、脚本提示与图片文字，并提供灵动视效、成就兼容、实体工具与汉化包导出。

仓库：[`ARC-MCBE-Addon-Auto-Localizer`](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)

产品短名：**弧光自动汉化工具**

## 作者信息

- **作者**: [DEVILENMO](https://github.com/DEVILENMO)
- **B 站**: [https://space.bilibili.com/37202522](https://space.bilibili.com/37202522)
- **邮箱**: DEVILENMO@gmail.com
- **组织**: [ARC Minecraft](https://github.com/ARC-Minecraft) / ARCStudio
- **版本**: 1.0.3
- **推荐 Python 版本**: 3.12+
- **UI 框架**: Flet 0.86

---

## 快速开始（普通用户）

1. 打开 [Releases](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer/releases) 下载最新 `exe`
2. 双击运行（Windows，无需安装 Python）
3. 右上角「设置」填写文本 / 图片 LLM 的 Base URL、API Key（及可选代理）
4. 在首屏选择要处理的模组，进入工具箱按步骤操作

本机需已安装 Minecraft Bedrock，工具会读取：

```
%APPDATA%\Minecraft Bedrock\Users\Shared\games\com.mojang\
  ├── resource_packs /
  ├── behavior_packs /
  ├── development_resource_packs /
  └── development_behavior_packs /
```

用户配置（含 API Key，**不会**进仓库）：

```
%APPDATA%\ARCStudio\弧光自动汉化工具\config.json
```

---

## 功能介绍

### 首屏：模组选择

- 扫描本地资源包 / 行为包，按 `manifest` UUID 依赖自动配对
- 卡片展示 RP / BP 徽章与包名
- 支持按中文 `pack.name` 等规则预览并整理模组文件夹名称

### ① 模组汉化

进入本页后会自动规范化 JSON / JS（内容无变化则跳过写盘）。

| 步骤 | 说明 |
|------|------|
| 语言文件汉化 | 确保 `zh_CN`、从英文 lang 复制并调用 LLM 批量翻译条目 |
| Display Name 汉化 | 扫描实体等 JSON 中的 `minecraft:display_name`，翻译后写回 |
| 脚本提示汉化 | 汉化 `sendMessage` / `form.title|button|label|body|toggle|…`、`setActionBar`、`tooltip` 等玩家可见字符串；跳过语言键与含 `.map/.join` 的复杂多行模板；写入前 `node --check` 校验，失败自动回退 |
| 汉化者署名 | 在包名后追加 `（名称汉化）`，默认 DEVILENMO，可在设置中改 |
| 一键汉化 | 按顺序执行：语言 → Display Name → 脚本 → 署名 |

### ② 图片汉化

独立页面：左侧列出模组内含图目录，右侧缩略图预览并勾选；只汉化选中文件。

- 写回时**强制保持原图像素宽高**（含异形比例）；模型输出尺寸不一致时会自动缩放回原分辨率
- 原图备份到同目录 `_backup/`
- 路径含 `book` / `guide`，或目录内图片名含 `page` 的目录会**置顶**并以醒目颜色标注「建议汉化」（guidebook 类贴图）
- 需在设置中配置支持图像输入/输出的图片 LLM

### ③ 灵动视效

- 检测资源包 `manifest.json` 的 `capabilities` 是否包含 `pbr`
- 一键添加 / 移除灵动视效（PBR）支持，并备份原 manifest

### ④ 成就兼容

- 检测资源包 / 行为包是否声明：

```json
"metadata": {
    "product_type": "addon"
}
```

- 一键为当前模组各包写入或移除该字段（保留 `authors` 等其它 metadata），使模组以附加包方式加载并保持成就可用

### ⑤ 实体工具

- 扫描行为包实体相关数据（如血量等），结果在界面文本框中展示，便于复制

### ⑥ 导出汉化包

- 将当前选中模组打包导出为可分发的压缩包（包内容位于压缩包根目录，含 `manifest.json`）

### 设置

- 默认汉化者名称
- 文本 LLM / 图片 LLM：Base URL、API Key、模型名、代理
- 连接测试与保存

### 其它

- 底部运行日志，支持一键复制全部日志
- 各耗时任务在后台线程执行，界面保持可响应

---

## 开发者运行

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
.\.venv\Scripts\python.exe mcbe_localization_hub.py
```

推荐 **Python 3.12+**。首次启动 Flet 桌面客户端时可能需要下载运行时；网络不通时可配置系统 / 环境代理后重试。

## 打包

```bash
flet pack mcbe_localization_hub.py -n mcbe_localization_hub ^
  -i assets\app_icon.ico --add-data "assets;assets" ^
  --product-name "弧光自动汉化工具" --company-name "ARCStudio" ^
  --product-version "1.0.3" --file-version "1.0.3" ^
  --hidden-import openai --hidden-import httpx -y
```

请使用项目 `.venv`（勿用臃肿的全局 conda 环境），产物在 `dist/`（已 gitignore）。正式版通过 GitHub Release 发布可双击运行的 `exe`。

## 目录说明

| 路径 | 说明 |
|------|------|
| `mcbe_localization_hub.py` | 启动入口（Flet） |
| `VERSION` | 当前版本号 |
| `utils/` | 业务逻辑 |
| `utils/fletui/` | Flet 界面 |
| `assets/` | 图标等资源 |
| `ui/` | 格式化等被 service 复用的辅助模块 |
| `requirements.txt` | 依赖锁定 |
| `LICENSE` | MIT |
| `.venv/` | 本地虚拟环境（不上传） |

## 版本

当前版本：**1.0.3**

### 更新说明

#### v1.0.3

- **窗口图标**：打包后从 `sys._MEIPASS/assets` 正确加载 `app_icon.ico`，标题栏不再显示 Flet 默认鱼标

#### v1.0.2

- **图片汉化预览修复**：修复工具栏 `Row(wrap=True)` 与 `expand` 冲突导致右侧整片灰屏（Flutter ErrorWidget）的问题；预览改为「缩略图 + 文件名 + 分辨率 + 勾选」列表
- **改名后路径同步**：语言/署名后按中文包名重命名文件夹时，可靠回写 `resource_pack_path` / `behavior_pack_path`，并刷新状态栏与图片目录，避免后续功能报路径不存在
- **图片目录体验**：长路径自适应多行显示；含 `book`/`guide` 或图片名含 `page` 的目录置顶并以品牌色标注「建议汉化」

#### v1.0.1

- **图片汉化独立页**：侧栏新增「图片汉化」；按目录预览缩略图，勾选后汉化，不再整目录一键硬翻
- **保持原分辨率**：汉化写回强制对齐原图像素宽高（含异形比例）；模型尺寸不一致时自动最近邻缩回
- **脚本提示**：支持 `.toggle` / `tooltip` 等表单文案；允许 `${Math.floor(...)}` 等简单函数插值；跳过含 `.map/.join` 的复杂多行模板，避免脚本语法被截断
- **成就兼容**：可为 RP/BP 写入或移除 `metadata.product_type = "addon"`
- **体验**：格式化与汉化步骤串行，避免日志交错；运行日志支持一键复制；JS 内容无变化时跳过写盘

#### v1.0.0

- 首个正式版：模组配对、语言 / Display Name / 脚本 / 署名、灵动视效、实体工具、导出汉化包与 Windows 一键 exe

## 许可与归属

本项目采用 [MIT License](LICENSE)。

主要作者 **DEVILENMO**（[B 站主页](https://space.bilibili.com/37202522)），归属 [ARC Minecraft](https://github.com/ARC-Minecraft) / ARCStudio。Issues 与反馈请到本仓库提出。
