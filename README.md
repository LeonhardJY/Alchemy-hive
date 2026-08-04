# weflow-agent

从 WeFlow 导出的微信聊天记录蒸馏出「人物 AI agent」，一键导出为 buzz `.agent.json`，拖进 Buzz 桌面端即可导入。本地优先：默认（不配置模型）走纯本地规则兜底，零网络调用；配置模型后蒸馏阶段会把聊天样本发往你填写的模型地址。

## 快速上手（10 分钟）

前置：Python 3.10+；用 [WeFlow](https://github.com/hicccc77/WeFlow) 导出私聊 JSON（见 [docs/WEFLOW_EXPORT.md](docs/WEFLOW_EXPORT.md)）。

```bash
# 方式一：从源码安装（推荐，当前阶段）
git clone https://github.com/<你的仓库>/weflow-agent && cd weflow-agent
pip install -e .
# 方式二：PyPI（发布后可用）
pip install weflow-agent
# 1. 解析聊天记录
weflow-agent import chat.json --name 张書源
# 2. 蒸馏 persona（配置 API key 获得最佳效果；不配则用规则兜底）
weflow-agent distill --name 张書源
# 3. 导出 buzz 快照
weflow-agent export --name 张書源
# 4. 打开 Buzz 桌面端 My Agents → 把 build/export/张書源.agent.json 拖进去
```

## 配置 LLM（可选，推荐）

复制 `.weflow-agent/config.toml.example` 为 `.weflow-agent/config.toml`，填入 OpenAI-compatible 的模型地址与 key（如 DeepSeek、OpenAI、本地 vLLM）：

```toml
[model]
base_url = "https://api.deepseek.com/v1"
api_key = "sk-..."
model = "deepseek-chat"
```

## 命令

| 命令 | 作用 |
|---|---|
| `weflow-agent import <文件> --name X` | 解析聊天 → 结构化消息 |
| `weflow-agent distill --name X` | 蒸馏 persona（LLM / 规则兜底） |
| `weflow-agent export --name X` | 导出 `.agent.json` |

## 隐私

默认不配模型时零网络调用；配置模型（推荐以获得更真实的表达）后，蒸馏会把你指定的人物聊天样本发送到所配置的模型服务地址，请确认信任该服务。产物含真实聊天内容，**分享到 GitHub 或发给他人前请自行脱敏**（替换姓名/号码）。
