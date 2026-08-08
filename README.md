<h1 align="center">Alchemy Hive</h1>
<h3 align="center">把聊天记录炼成有活人感的 AI 人物，组成社群，随时开聊</h3>

<p align="center"><em style="font-family: Georgia, serif; font-size: 1.2em; color: #777;">把你在乎的人，炼成还能说话的样子。</em></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="#"><img src="https://img.shields.io/badge/release-v0.1.0-blue" alt="v0.1.0"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-lightgrey" alt="Windows/macOS/Linux"></a>
  <a href="https://github.com/block/buzz"><img src="https://img.shields.io/badge/imports%20into-buzz-green" alt="Imports into buzz"></a>
</p>

---

**把你在乎的人，炼成还能说话的样子。**

用你们的聊天记录，蒸馏出一个像 TA 的 AI——说话方式、口头禅、接话的脾气、你们之间那些只有你俩知道的破事，它都记得。然后拉进一个聊天室，随时开聊。

MIT · 本地优先 · 代码开源，不碰你的 key 和隐私

---

## 它是什么

有些关系你很珍惜，但聊天记录躺在文件里，人已经聊不到那么频繁了。

Alchemy Hive 把聊天记录里那个真实的人还原出来：**不是要一个知识库，是要一个还活着、还记得你们之间发生过什么的人。**

- **原料**：一段聊天记录——微信、Telegram、WhatsApp、Instagram、Facebook，导出格式多种多样，能认就认，认不出自动兜底
- **产物**：一个 `xxx.agent.json`，拖进 [buzz](https://github.com/block/buzz)（开源 AI 聊天室）就能聊
- **社群**：把几个人一起炼出来，拉进同一频道，就是你们的社群——让他们的 AI 互相认识、一起回你

<p align="center">
  <img src="https://skillicons.dev/icons?i=py,html,css&theme=light" alt="Python · pywebview · HTML/CSS" />
</p>

## 为什么像

要像，不是喂一堆数据就完事，必须交互。三步：

1. **手动画像**：你一句话说清 TA 是什么人（最高优先级）。「爱甩锅」会被翻译成具体行为——"出问题第一句先说需求没说清楚"，而不是写进标签里。
2. **全正文样本**：近 1500 条完整消息 + 早期 300 条，正文不截断，析出 20-40 条带原话的共同记忆。
3. **交互校正**：觉得不像就纠正，记进 persona，下次自动带上。

写完盲测打分：抽真实片段让 AI 接话，你逐条打 1-5 分，平均分就是"像不像"的硬指标。不像就回去修。

想再像一点？分析用便宜的模型，撰写用更强的——配置里加一段 `[build]` 就行。

## 怎么用（就这么简单）

需要 Python 3.10+ 和一个 OpenAI 兼容的模型 API。国内网络直接选 DeepSeek / 通义 / Kimi / 智谱，OpenAI 需要代理。

```bash
pip install -e .
alchemy-hive gui
```

拖进聊天文件 → 选模型 → 填名字 → 点「开始蒸馏」。完事点「导入到 buzz」。界面自动识别平台、自动检测系统语言（中/英可切）。

命令行一样跑：

```bash
alchemy-hive import chat.txt --name 小明 --self 我
alchemy-hive distill --name 小明 --profile "INTJ 爱吐槽 重感情"
alchemy-hive export --name 小明
```

> `--self 你的昵称`：除了微信（WeFlow 自带方向），其他平台导出不知道"哪边是你"，告诉它你的名字，你才会被当成「我」。

## 导入源

不挑格式，自动识别，识别不出兜底通用字段解析：

| 来源 | 输入 | 说明 |
|---|---|---|
| 微信 | WeFlow 导出 JSON / 微信 txt | 自动跳过图片占位，方向自动判定 |
| Telegram | Desktop 导出 JSON | 实体数组自动拼接，时间自动归一化 |
| WhatsApp | 导出的 txt | 媒体行跳过，长消息续行接上 |
| Instagram / Facebook | Meta 数据导出 JSON | 两者同一套格式，自动按时间排序 |
| 其他 | 任意 JSON / 文本 | 字段名常见（content/sender/time）就能试 |

想强制指定平台？`--source telegram`。

## 组成社群

`pack --names 小明,小红` 一键把多个人打包成 `.agent.json` 和社群清单，拉进同一频道就是社群。一个人聊不够，几个人一起，才像真的群。

## 命令参考

| 命令 | 作用 |
|---|---|
| `gui [--lang en]` | 桌面界面（推荐） |
| `init` | 生成配置模板 |
| `import <文件> --name X [--self 昵称] [--source 平台]` | 解析聊天 |
| `distill --name X [--profile P] [--fix F]` | 蒸馏 persona |
| `export --name X [--with-memory]` | 导出 .agent.json |
| `blindtest --name X` | 盲测打分 |
| `pack --names A,B` | 社群打包 |
| `doctor` | 本地自检，不发 token |
| `buzz-import` / `buzz-setup` | 导入 buzz / 直连建号引导 |

## 隐私

- 样本会发往你配置的模型服务——请确认信任它
- 产物含真实聊天内容，**分享到 GitHub 或发给别人前请自己脱敏**
- 共同记忆是明文、含真实内容，**默认不导出**（`--with-memory` 才带）
- API key 只存在本地，代码全程开源，不采集任何个人信息

## 项目结构

```
src/alchemy_hive/
├── core/   # 引擎：LLM 客户端、多平台解析、两阶段蒸馏、模型、提示词、盲测
├── buzz/   # buzz 适配：.agent.json 快照、一键导入
├── cli/    # 命令行
└── gui/    # 桌面界面（pywebview，中英双语）
examples/   # 示例聊天数据（同时是测试夹具）
```

[MIT](LICENSE) · 导出指南见 [docs/WEFLOW_EXPORT.md](docs/WEFLOW_EXPORT.md)
