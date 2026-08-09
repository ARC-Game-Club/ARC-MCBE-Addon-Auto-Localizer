# 弧光我的世界基岩 Addon 自动汉化器

**版本：1.0.0**

[ARC Minecraft](https://github.com/ARC-Minecraft) 出品的 Minecraft 基岩版（MCBE）Addon / 模组桌面汉化工具。自动扫描并配对资源包与行为包，借助 LLM 翻译语言文件、Display Name、脚本提示与图片文字，并提供灵动视效、成就兼容、实体工具与汉化包导出。

仓库：[`ARC-MCBE-Addon-Auto-Localizer`](https://github.com/ARC-Minecraft/ARC-MCBE-Addon-Auto-Localizer)

产品短名：**弧光自动汉化工具**

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
| 图片汉化（可选） | 选择含图片的子目录，调用图片 LLM 翻译贴图内文字 |

### ② 灵动视效

- 检测资源包 `manifest.json` 的 `capabilities` 是否包含 `pbr`
- 一键添加 / 移除灵动视效（PBR）支持，并备份原 manifest

### ③ 成就兼容

- 检测资源包 / 行为包是否声明：

```json
"metadata": {
    "product_type": "addon"
}
```

- 一键为当前模组各包写入或移除该字段（保留 `authors` 等其它 metadata），使模组以附加包方式加载并保持成就可用

### ④ 实体工具

- 扫描行为包实体相关数据（如血量等），结果在界面文本框中展示，便于复制

### ⑤ 导出汉化包

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

首次启动 Flet 桌面客户端时可能需要下载运行时；网络不通时可配置系统 / 环境代理后重试。

## 打包

```bash
flet pack mcbe_localization_hub.py -n mcbe_localization_hub ^
  -i assets\app_icon.ico --add-data "assets;assets" ^
  --product-name "弧光自动汉化工具" --company-name "ARCStudio" ^
  --hidden-import openai --hidden-import httpx -y
```

产物在 `dist/`（已 gitignore）。正式版会通过 GitHub Release 发布可双击运行的 `exe`。

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
| `.venv/` | 本地虚拟环境（不上传） |

## 版本

当前版本：**1.0.0**

## 许可与归属

ARC Minecraft / ARCStudio。Issues 与反馈请到本仓库提出。
