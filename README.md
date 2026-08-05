# weflow-agent

从 WeFlow 导出的微信聊天记录蒸馏出「人物 AI agent」，一键导出为 buzz `.agent.json`，拖进 Buzz 桌面端即可导入。蒸馏必须配置 LLM（OpenAI-compatible），支持 CLI 和桌面 GUI 两种方式。

## 快速上手（10 分钟）

前置：Python 3.10+；用 [WeFlow](https://github.com/hicccc77/WeFlow) 导出私聊 JSON（见 [docs/WEFLOW_EXPORT.md](docs/WEFLOW_EXPORT.md)）。

```bash
# 方式一：从源码安装（推荐，当前阶段）
git clone https://github.com/<你的仓库>/weflow-agent && cd weflow-agent
pip install -e .
# 方式二：PyPI（发布后可用）
pip install weflow-agent
```

### 图形界面（推荐）

```bash
weflow-agent gui
```

在界面中填写聊天文件路径、人物名，以及 base_url / api_key / model，点击「开始蒸馏」即可一键完成 import → distill → export。产物在 `build/export/<人物名>.agent.json`，拖入 buzz 桌面端导入。

### 命令行

```bash
# 1. 解析聊天记录
weflow-agent import chat.json --name 张書源
# 2. 蒸馏 persona（需配置模型 key）
weflow-agent distill --name 张書源
# 3. 导出 buzz 快照
weflow-agent export --name 张書源
# 4. 打开 Buzz 桌面端 My Agents → 把 build/export/张書源.agent.json 拖进去
```

## 配置 LLM（必需）

蒸馏阶段会把你指定的人物聊天样本发往所配置的模型服务地址进行 persona 分析，**必须**配置 API key，无 key 会报错。

复制 `.weflow-agent/config.toml.example` 为 `.weflow-agent/config.toml`，填入 OpenAI-compatible 的模型地址与 key（如 DeepSeek、OpenAI、本地 vLLM）：

```toml
[model]
base_url = "https://api.deepseek.com/v1"
api_key = "sk-..."
model = "deepseek-chat"
```

使用图形界面时，直接在界面上填写这三个字段即可，无需修改配置文件。

## 图形界面

`weflow-agent gui` 启动 Tkinter 桌面窗口，提供以下功能：

- **聊天文件**：选择 WeFlow 导出 JSON 或微信 txt
- **人物名**：人物显示名称
- **模型配置**：base_url、api_key、model（必填）
- **一键蒸馏**：import → distill → export 三步串联执行，日志实时输出
- **产物**：`build/export/<人物名>.agent.json`

## 命令

| 命令 | 作用 |
|---|---|
| `weflow-agent gui` | 启动桌面图形界面（推荐） |
| `weflow-agent import <文件> --name X` | 解析聊天 → 结构化消息 |
| `weflow-agent distill --name X` | 蒸馏 persona（LLM） |
| `weflow-agent export --name X` | 导出 `.agent.json` |
| `weflow-agent blindtest --name X` | 盲测验证（真实 vs agent 接话，人工打分） |
| `weflow-agent pack --names A,B` | 批量导出多 agent + 社群清单 |

## 盲测验证（像不像）

`weflow-agent blindtest --name 张書源` 会从聊天记录抽真实片段，让蒸馏出的 agent 接话，你逐条打分（1-5），最后给出平均分——验证蒸馏质量，不满意就重新 distill 或调模型。

```bash
weflow-agent blindtest --name 张書源 --n 5
```

## 社群（多 agent）

把多个蒸馏出的人物批量导出，导入 buzz 后建群形成社群：

```bash
weflow-agent pack --names 张書源,张鹏博
# 产出 build/export/张書源.agent.json、build/export/张鹏博.agent.json + community.json（群组清单）
```

按 `community.json` 的 setup 步骤：逐个把 `.agent.json` 拖入 buzz 导入 → 新建频道（默认 #friends）把 agent 加入 → 在群里 @agent 触发对话。subscribe/triggers 是建议，导入后可在 buzz UI 微调。

## 隐私

蒸馏会把你指定的人物聊天样本发送到所配置的模型服务地址，请确认信任该服务。产物含真实聊天内容，**分享到 GitHub 或发给他人前请自行脱敏**（替换姓名/号码）。
