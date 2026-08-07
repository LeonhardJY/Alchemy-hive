# Alchemy Hive

把微信聊天记录蒸馏成有「活人感」的 AI 朋友，一键导入 [buzz](https://github.com/block/buzz) 开聊，随时组建无数个 AI 社群。

**完全开源（MIT）· 本地优先 · 不会获取你的任何个人信息和 API key**

---

## 它能做什么

- **聊天记录 → AI 朋友**：把 WeFlow 导出的微信聊天（或微信 txt）蒸馏成某个人的 AI agent
- **像真人**：对齐 dot-skill 的交互式蒸馏——手动画像 + 全正文样本 + 交互校正
- **一键进 buzz**：打开导出文件夹 + 复制路径，一步送到 buzz 桌面端；开发者可用 buzz-cli 直连建号
- **社群**：多 agent 打包，拉进同一频道就是社群，想建几个建几个

## 快速开始（10 分钟）

### 1. 安装

```bash
git clone <你的仓库>/alchemy-hive && cd alchemy-hive
pip install -e .
```

### 2. 导出聊天记录

用 [WeFlow](https://github.com/hicccc77/WeFlow) 导出私聊 JSON（推荐），或微信导出的 txt。
详细步骤与格式说明见 [docs/WEFLOW_EXPORT.md](docs/WEFLOW_EXPORT.md)。

### 3. 配置模型

蒸馏需要 OpenAI-compatible 的模型 API（必需）：

```bash
alchemy-hive init      # 生成 .alchemy-hive/config.toml
```

编辑 `.alchemy-hive/config.toml` 填入 base_url / api_key / model：

```toml
[model]
base_url = "https://api.deepseek.com/v1"
api_key = "sk-..."
model = "deepseek-v4-flash"
```

> 国内网络直接用 DeepSeek / 通义千问 / Kimi / 智谱 等国内直连模型；**OpenAI 需代理**。GUI 里可下拉选择，无需手填。

### 4. 开始蒸馏

**图形界面（推荐）**：

```bash
alchemy-hive gui
```

拖入聊天文件 → 选模型 → 填名字与性格画像 → 点「开始蒸馏」。

**命令行**：

```bash
alchemy-hive import chat.json --name 小明
alchemy-hive distill --name 小明 --profile "INTJ 摩羯座 爱吐槽"   # 手动画像（最高优先级）
alchemy-hive export --name 小明
```

### 5. 导入 buzz 开聊

产物在 `build/export/小明.agent.json`。GUI 里点「导入到 buzz」自动打开文件夹并复制路径；
在 buzz 桌面端 My Agents → 导入 → 粘贴路径（或把文件拖进窗口），然后 @ 它开聊。

---

## 图形界面

`alchemy-hive gui` 按四步引导：**原料导入 → 蒸馏人物 → 成品文件 → 导入buzz**。

- **拖拽上传**：把聊天文件拖进来自动识别格式与消息数
- **模型下拉**：DeepSeek / OpenAI / 通义千问 / Kimi / 智谱 / 豆包 / 混元 / SiliconFlow / 本地 Ollama / vLLM，自动填地址与模型名
- **性格画像**：填得越具体越像 TA（最高优先级）
- **进度与日志**：转圈「正在蒸馏中…」+ 实时日志（显示实际调用端点）
- **成功横幅 + 导入提示**：完成后高亮「导入到 buzz」，一键进 buzz

## 蒸馏质量（交互式，对齐 dot-skill）

要像真人，必须交互——纯一键丢文件不够。三步：

1. **手动画像**（最高优先级）——一句话说清 TA 是什么样的人，标签会翻译成具体行为规则：

   ```bash
   alchemy-hive distill --name 小明 --profile "INTJ 摩羯座 爱吐槽 重感情 游戏宅"
   ```

2. **全正文样本**——取近期 1500 条完整消息 + 早期 300 条（不截断正文），分析出 20-40 条带原话的共同记忆。

3. **交互校正**——觉得不像就纠正，校正会记入 persona：

   ```bash
   alchemy-hive distill --name 小明 --fix "他不会这样，他其实很细心"
   ```

**产物** `build/persona/小明.md`（≥400 行），结构包含：

`Layer 0 核心性格 / 身份关系 / 这段关系·一路走来 / 这段关系意味着什么 / 表达风格 / 情绪逻辑 / 冲突修复 / 记忆库（每条含「关系意义」）/ 记忆余像`，外加校正记录。

**撰写用更强模型（可选）**：分析用便宜的 v4-flash，撰写用更强的模型（`.agent.json` 质量更高）——在 config 加 `[build]` 段：

```toml
[model]
base_url = "https://api.deepseek.com/v1"
api_key = "..."
model = "deepseek-v4-flash"

[build]   # 可选：撰写阶段用更强模型
base_url = "https://api.deepseek.com/v1"
api_key = "..."
model = "deepseek-v4-pro"
```

**盲测验证「像不像」**：

```bash
alchemy-hive blindtest --name 小明 --n 5
```

抽真实聊天片段让 agent 接话，你逐条打分（1-5），平均分就是蒸馏质量的量化指标。

## 导入 buzz

### 主路径（傻瓜级，100% 可用）

buzz 桌面端只开放 UI 导入（My Agents → 导入 / 拖入窗口），没有命令行接口。所以「导入到 buzz」把「找文件 + 复制路径」压成一步：

- `--name` 不填 → **自动导入全部成品**（适配多人物社群）
- 找不到成品 → 友好提示「先开始蒸馏」
- 剪贴板/打开文件夹失败 → 提示手动路径

### 开发者直连（buzz-cli，免手动）

buzz-cli 可走 relay 直接建号：

```bash
alchemy-hive buzz-setup --channel <频道UUID>   # 检查 buzz-cli/密钥/relay、列出频道、存配置
alchemy-hive buzz-import --name 小明            # 之后免填直连建号
```

需要：buzz-cli + `BUZZ_PRIVATE_KEY`（Nostr 私钥）+ 可达 relay。`buzz-setup` 会逐步检查缺啥教啥。

## 命令参考

| 命令 | 作用 |
|---|---|
| `gui` | 桌面图形界面（推荐） |
| `init` | 生成配置模板（config.toml） |
| `import <文件> --name X` | 解析聊天 → 结构化消息 |
| `distill --name X [--profile P] [--fix F]` | 蒸馏 persona（支持手动画像与校正） |
| `export --name X [--with-memory]` | 导出 `.agent.json` |
| `buzz-import [--name X] [--channel C]` | 一键导入 buzz（不填名称导入全部） |
| `buzz-setup [--channel C]` | 开发者：buzz-cli 直连建号引导 |
| `doctor` | 本地自检（不发 token） |
| `blindtest --name X` | 盲测对拍评分 |
| `pack --names A,B [--with-memory]` | 多 agent 社群打包 |

## 排查问题（不用试错式调 API）

```bash
alchemy-hive doctor
```

`doctor` 不发 LLM 请求、不消耗 token：`GET {base_url}/models` 探测连通性——**200=密钥有效；401=端点可达需鉴权（正常）；连接超时/失败=被墙或需代理**。国内网络下 OpenAI 会探测失败，DeepSeek/通义/Kimi 等国内直连正常。大聊天记录（几十 MB）已支持流式解析，10 万条消息秒级完成。

## 项目结构

```
alchemy-hive/
├── src/alchemy_hive/
│   ├── core/      # 蒸馏引擎：LLM 客户端、解析、模型、提示词、安全
│   ├── buzz/      # buzz 适配：.agent.json 快照、一键导入
│   ├── cli/       # 命令行入口
│   └── gui/       # 桌面界面（pywebview）
├── examples/      # 示例聊天数据（同时作为测试 fixture）
├── tests/         # 测试套件
├── docs/          # 文档（WeFlow 导出指南）
└── .alchemy-hive/ # 本地配置（config.toml 含 API key，git 忽略）
```

## 隐私与安全

- 聊天样本会发往你配置的模型服务，请确认信任该服务
- 产物含真实聊天内容，**分享到 GitHub 或发给他人前请自行脱敏**（替换姓名/号码）
- 共同记忆是明文、含真实内容，**默认不导出**（`--with-memory` 才包含）
- API key 只保存在本地配置/界面，不会被上传

## 许可

[MIT License](LICENSE)
