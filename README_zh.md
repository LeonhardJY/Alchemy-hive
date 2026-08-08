<h1 align="center">Alchemy Hive</h1>
<h3 align="center">聊天记录 → 有活人感的 AI 人物 → buzz .agent.json</h3>

<p align="center"><em style="font-family: Georgia, serif; font-size: 1.1em; color: #777;">两阶段 LLM 蒸馏 · 多平台导入 · buzz 一键集成</em></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="#"><img src="https://img.shields.io/badge/release-v0.1.0-blue" alt="v0.1.0"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-lightgrey" alt="Windows/macOS/Linux"></a>
  <a href="https://github.com/block/buzz"><img src="https://img.shields.io/badge/imports%20into-buzz-green" alt="Imports into buzz"></a>
</p>

<p align="center"><a href="README.md">English</a> · <b>中文</b></p>

---

## 它做什么

把一段聊天记录解析成结构化消息，用两阶段 LLM 蒸馏出 persona，导出成 buzz 桌面端可直接导入的 `.agent.json`。

```
聊天文件（微信 / Telegram / WhatsApp / Instagram / Facebook / 通用）
  → parser：detect_source 采样 64KB 识别平台；--self 归一化「我」；时间戳统一
  → distill：
      analyze   全正文样本（近期 1500 条 + 早期 300 条，不截断）→ 结构化 JSON 分析
      build     基于分析 → ≥400 行 persona Markdown（[build] 段可覆盖更强撰写模型）
      ├── --profile  手动画像（行为规则优先于聊天记录）
      └── --fix      交互校正（corrections 累积进 persona）
  → blindtest：真实回复 vs agent 接话，1-5 分人工评分
  → export：buzz-agent-snapshot v1 格式 .agent.json
  → buzz-import / pack：导入 buzz / 多 agent 社群打包
```

## 特点

- **多平台导入**：采样文件前 64KB 自动识别 WeFlow JSON、微信 txt、Telegram JSON、WhatsApp txt、Instagram/Facebook（Meta 共用一套格式）；识别失败回退通用字段探测（content/sender/time 等常见别名）
- **时间归一化**：Telegram ISO、WhatsApp `MM/DD/YY, h:mm AM/PM`、Meta `timestamp_ms` 统一转为 `YYYY-MM-DD HH:MM:SS`；Meta 导出是新的在前，自动按时间升序排序，保证"近期样本"取对
- **方向判定**：WeFlow 用 `isSend` 字段；其余平台导出无方向标记，用 `--self 你的昵称` 指定，消息发送者归一化为「我」
- **两阶段蒸馏**：analyze（结构化分析 + 20-40 条带原话的共同记忆）→ build（长 persona 正文）；`[build]` 配置段可换更强模型撰写
- **盲测**：抽真实片段让 agent 接话，1-5 分人工打分，平均分作为"像不像"的量化指标
- **GUI**：pywebview 桌面端，拖拽上传、平台/供应商下拉、中英双语（`--lang`，运行时右上角可切）
- **buzz 适配**：快照格式对齐 buzz 桌面端；导入压成"打开文件夹 + 复制路径"一步，不填名称自动导入全部成品

## 快速开始

### 依赖

- Python ≥ 3.10
- OpenAI-compatible 模型 API（`base_url` / `api_key` / `model`），国内可选 DeepSeek / 通义 / Kimi / 智谱

### 安装

```bash
git clone https://github.com/LeonhardJY/Alchemy-hive && cd Alchemy-hive
pip install -e .
alchemy-hive init    # 生成 .alchemy-hive/config.toml
```

### 蒸馏

```bash
alchemy-hive gui     # 图形界面
```

```bash
alchemy-hive import chat.txt --name 小明 --self 我
alchemy-hive distill --name 小明 --profile "INTJ 爱吐槽" --fix "他不会这样"
alchemy-hive export --name 小明 --with-memory
```

聊天记录导出方式见 [docs/WEFLOW_EXPORT_ZH.md](docs/WEFLOW_EXPORT_ZH.md)。

## 输入格式

自动识别，识别失败兜底通用字段解析；`--source <平台>` 可强制指定。

| 平台 | 输入 | 判定特征 | 时间来源 |
|---|---|---|---|
| 微信 | WeFlow 导出 JSON | `isSend` / `msgContent` | `createTime` |
| 微信 | 导出 txt | `YYYY-MM-DD HH:MM:SS '发送者'` 两行格式 | 行首时间戳 |
| Telegram | Desktop 导出 JSON | `messages[{type,date,from,text}]` | `date`（ISO） |
| WhatsApp | 导出 txt | `[MM/DD/YY, h:mm AM/PM] 发送者: 内容` | 12 小时制 |
| Instagram / Facebook | Meta 数据导出 JSON | `sender_name` / `content` / `timestamp_ms` | 毫秒时间戳 |
| 其他 | 任意 JSON / txt | `content` / `sender` / `time` 字段探测 | 原样保留 |

## 命令

| 命令 | 说明 |
|---|---|
| `gui [--lang en]` | 桌面图形界面（中/英双语） |
| `init` | 生成配置模板 |
| `import <文件> --name X [--self 昵称] [--source 平台]` | 解析聊天 → 结构化消息 |
| `distill --name X [--profile P] [--fix F]` | 蒸馏 persona |
| `export --name X [--with-memory]` | 导出 `.agent.json` |
| `blindtest --name X [--n N]` | 盲测对拍评分 |
| `pack --names A,B [--channel C]` | 多 agent 社群打包 |
| `doctor` | 本地自检端点连通性（不发 LLM 请求） |
| `buzz-import` / `buzz-setup` | 导入 buzz / buzz-cli 直连建号引导 |

## 项目结构

```
src/alchemy_hive/
├── core/   # 引擎：LLM 客户端、多平台解析、两阶段蒸馏、模型、提示词、盲测
├── buzz/   # buzz 适配：.agent.json 快照、一键导入
├── cli/    # 命令行（typer）
└── gui/    # 桌面界面（pywebview，中英双语）
examples/   # 示例聊天数据（同时是测试夹具）
```

## 隐私

- 聊天样本会发往你配置的模型服务
- 产物 `.agent.json` 含真实聊天内容，发布前自行脱敏
- 共同记忆默认不导出（`--with-memory` 才包含）
- API key 仅存本地

[MIT](LICENSE)
