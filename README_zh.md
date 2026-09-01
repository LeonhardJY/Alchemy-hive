<h1 align="center">Alchemy Hive</h1>

<p align="center">
  <em>把聊天记录蒸馏成有温度的 AI 朋友。</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://github.com/LeonhardJY/Alchemy-hive/actions"><img src="https://github.com/LeonhardJY/Alchemy-hive/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-lightgrey" alt="Windows/macOS/Linux"></a>
  <a href="https://github.com/block/buzz"><img src="https://img.shields.io/badge/imports%20into-buzz-green" alt="Imports into buzz"></a>
</p>

<p align="center"><a href="README.md">English</a> · <b>中文</b></p>

---

## 为什么做这个？

微信聊天、Telegram 对话、WhatsApp 群组、Discord 频道、Slack 消息——几年的回忆锁在聊天记录里，你可能再也不会翻看。

**Alchemy Hive** 用任意 OpenAI 兼容模型（DeepSeek、通义千问、Kimi、Ollama 等）把这些对话蒸馏成一个鲜活的人物画像。导出到 [buzz](https://github.com/block/buzz)、SillyTavern 或任何支持 system prompt 的平台——一个属于你的数字回声。

```
你的聊天文件 ──→ 解析器 ──→ 两阶段 LLM 蒸馏 ──→ PersonaDoc ──→ 多格式导出
  (10 大平台：         识别平台、           分析 + 撰写：            (system prompt
  微信 /              归一化时间、         结构化分析 →             .txt / buzz
  Telegram /          过滤媒体)           400+ 行角色画像           .agent.json /
  WhatsApp /                               带真实原话               SillyTavern)
  Discord /
  Slack /
  iMessage /
  QQ /
  Instagram /
  Facebook)
```

## 架构

<p align="center">
  <a href="docs/architecture.html"><b>🔗 交互式架构图</b></a>
</p>

<p align="center"><em>点击查看完整架构——悬停查看详情，点击组件聚焦。</em></p>

```
                    ┌─────────────┐
                    │  LLM API    │
                    │  OpenAI 兼容 │
                    └──────┬──────┘
                           │ LLM 调用
聊天源 ──→ 解析器 ──→ 蒸馏引擎 ──→ PersonaDoc ──→ 导出器
 (10 平台)  (识别+解析)  (分析+撰写)  (通用格式)    (3 种格式)
                           │                        │
                           │                        ├──→ System Prompt (.txt)
                           │                        ├──→ Buzz (.agent.json)
                           │                        └──→ SillyTavern (角色卡 v2)

              CLI (13 命令)     GUI (pywebview)
              聊天测试          自动评分 (LLM-as-judge)
```

## 效果预览

<!-- 在这里添加录屏 GIF 或截图。
     录屏工具：https://github.com/nicedoc/screenrecord 或 OBS。
     建议流程：拖入文件 → 填写名称 → 点击"开始蒸馏" → 查看日志 → 点击"导入 buzz" -->

<p align="center"><em>界面截图即将添加——运行 <code>alchemy-hive gui</code> 亲自体验！</em></p>

## 快速开始

### 安装

```bash
pip install alchemy-hive
alchemy-hive init    # 生成 .alchemy-hive/config.toml，填入你的 API key
alchemy-hive doctor  # 检查配置和端点连通性
```

或从源码安装：

```bash
git clone https://github.com/LeonhardJY/Alchemy-hive && cd Alchemy-hive
pip install -e .
alchemy-hive init
alchemy-hive doctor
```

### 启动图形界面

```bash
alchemy-hive gui              # 桌面端，支持拖拽上传
alchemy-hive gui --lang en    # 英文界面
```

### 或使用命令行

```bash
# 1. 导入聊天记录
alchemy-hive import chat.txt --name 小明 --self 我 --source auto

# 2. 蒸馏画像
alchemy-hive distill --name 小明 --profile "INTJ 爱吐槽 重感情"

# 3. 导出给 buzz
alchemy-hive export --name 小明 --format buzz

# 4. 导入 buzz
alchemy-hive buzz-import --name 小明
```

### 支持的聊天导出

| 平台 | 导出方式 | 格式 |
|------|---------|------|
| **微信** | [WeFlow](https://github.com/nicedoc/screenrecord) 桌面端导出 | JSON |
| **微信** | 微信电脑端 → 备份 → txt | txt |
| **Telegram** | 桌面端 → 设置 → 高级 → 导出 | JSON |
| **WhatsApp** | 手机 → 设置 → 聊天 → 导出聊天 | txt |
| **Discord** | DiscordChatExporter 导出聊天 → CSV/JSON | JSON |
| **Slack** | 工作区设置 → 导入/导出数据 | JSON |
| **iMessage** | iExplorer 或 iMazing → 导出聊天 → CSV | CSV/TXT |
| **QQ** | QQMsgExport 或类似工具 → JSON 导出 | JSON |
| **Instagram** | 设置 → 隐私 → 下载你的信息 | JSON |
| **Facebook** | 设置 → 你的 Facebook 信息 → 下载 | JSON |

详细导出教程：[中文](docs/WEFLOW_EXPORT_ZH.md) · [English](docs/WEFLOW_EXPORT_EN.md)

## 工作原理

**第一阶段——分析**：采样近期消息（1500 条）+ 早期消息（300 条），送入 LLM 做结构化分析——性格、表达习惯、20-40 条带原话的共同记忆。

**第二阶段——撰写**：基于分析结果生成 400+ 行角色画像 Markdown。撰写失败时自动降级为结构化渲染，保证非空。

**质量验证**：
- `blindtest`——真实回复 vs agent 接话，1-5 分人工评分
- `doctor`——启动前检查配置和端点连通性（不消耗 token）
- 交互校正——`--fix` 在多次蒸馏间累积纠正记录

## 功能特点

- **10 大平台**——微信（WeFlow JSON + txt）、Telegram、WhatsApp、Discord、Slack、iMessage（CSV/TXT）、QQ、Instagram/Facebook、通用 JSON/txt
- **自动识别**——采样 64KB 识别平台；失败后回退字段探测
- **两阶段蒸馏**——结构化分析 → 带真实原话的长画像
- **增量蒸馏**——`--incremental` 将新消息合并到已有画像
- **插件架构**——source adapter + exporter adapter；一个文件即可添加新平台
- **多格式导出**——system prompt（.txt）、buzz（.agent.json）、SillyTavern（角色卡 V2），可扩展
- **CSV 支持**——iMessage CSV 导出原生解析；解析器接受 JSON/txt/CSV
- **盲测对拍**——量化「像不像」的人工评分
- **交互校正**——`--fix` 和 `--profile` 跨次蒸馏迭代优化
- **图形界面**——pywebview 桌面端，拖拽上传，中英双语
- **buzz 集成**——一键导入 [buzz](https://github.com/block/buzz) 社群
- **多供应商**——DeepSeek、通义千问、Kimi、智谱、Ollama、vLLM 或任意 OpenAI 兼容 API
- **隐私优先**——所有数据本地处理；共同记忆默认不导出

## 命令速查

| 命令 | 说明 |
|------|------|
| `alchemy-hive gui` | 启动桌面图形界面 |
| `alchemy-hive init` | 生成配置模板 |
| `alchemy-hive doctor` | 检查配置和连通性（不消耗 token） |
| `alchemy-hive import <文件> --name X` | 解析聊天 → 结构化消息 |
| `alchemy-hive distill --name X` | 蒸馏画像 |
| `alchemy-hive distill --name X --incremental` | 增量模式：将新消息合并到已有画像 |
| `alchemy-hive export --name X --format text/buzz/all` | 导出画像（多格式） |
| `alchemy-hive export-all --name X` | 一键导出所有格式 |
| `alchemy-hive chat --name X` | 与画像角色聊天 |
| `alchemy-hive evaluate --name X` | 自动评分（LLM-as-judge） |
| `alchemy-hive blindtest --name X` | 盲测评分（1-5） |
| `alchemy-hive pack --names A,B` | 多 agent 社群打包 |
| `alchemy-hive buzz-import` | 导入 buzz |

## 配置

`alchemy-hive init` 生成 `.alchemy-hive/config.toml`：

```toml
[model]
base_url = "https://api.deepseek.com/v1"
api_key = "sk-你的-key"
model = "deepseek-v4-flash"

# 可选：用更强模型撰写画像
# [build]
# base_url = "https://api.deepseek.com/v1"
# api_key = "sk-你的-key"
# model = "deepseek-chat"
```

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)（开发环境搭建与贡献指南）。

## 名字的含义

**Alchemy（炼金术）**——点石成金。聊天记录是原料，蒸馏出的 persona 是成品：同一份材料，变成能对话的样子。

**Hive（蜂巢）**——蜂群，也是 hive mind。一个 agent 是一只蜜蜂；几个一起拉进一个频道，就成了一窝蜂——会聊天、会记住、会一起回你的社群。

## 隐私

- 聊天样本会发往**你**配置的模型服务
- 产物 `.agent.json` 含真实聊天内容，发布前自行脱敏
- 共同记忆默认不导出（`--with-memory` 才包含）
- API key 仅存本地

## 许可证

[MIT](LICENSE)
