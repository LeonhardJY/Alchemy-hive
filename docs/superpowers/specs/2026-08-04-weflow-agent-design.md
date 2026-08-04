# weflow-agent — 设计文档

> 日期：2026-08-04
> 状态：已确认（brainstorming）
> 目标：开源 CLI，让有编程基础的人从 WeFlow 导出的微信聊天记录蒸馏出人物 AI agent，一键导入 buzz 形成 agent 社群。

---

## 1. 概述

把「微信聊天记录 → 人物 AI agent → buzz 社群」的完整流程做成一个可复用的开源 CLI。

**为什么值得做**：GitHub 上无现成完整闭环（已查证）。最接近的 `xmh1011/wechat-skill-distill` 只覆盖「导出 → 蒸馏成 skill」，不接 buzz，产物不兼容 buzz 的 `.agent.json` 快照。weflow-agent 补上闭环并内建质量保障。

**核心理念**：蒸馏引擎与 buzz 解耦——`core/` 只负责把聊天记录蒸馏成结构化的人物 persona，`buzz/` 只是导出目标之一。未来可扩展其他平台。

---

## 2. 目标与非目标

### 目标
- 一条命令从 WeFlow 导出 JSON 跑出人物 agent
- 支持同事 / 关系 / 名人三类人物（继承 dot-skill 分类）
- 导出为 buzz `.agent.json` 快照（单 agent），并可生成多 agent 社群 pack
- 内建「表达硬规则 + 真实例句」强制注入，避免 AI 输出书面语
- 从聊天记录提取记忆条目，让 agent 自带共同回忆
- 内建盲测对拍（blindtest），蒸馏完即可验证「像不像」

### 非目标
- 不做微信数据导出（交给 WeFlow，见依赖）
- 不做 GUI（M4 阶段，先 CLI）
- 不做云端 / 在线服务（本地优先，数据不出本机）
- 不做聊天记录脱敏引擎（用户自选；仅提供敏感内容提醒）

---

## 3. 用户画像与上手路径

**目标用户**：有编程基础（会装 Python / 会跑命令行）的人。

**上手路径**：
```bash
pip install weflow-agent          # 或 pipx install
weflow-agent init                  # 生成配置模板 + 教程
# 1. 用 WeFlow 导出私聊 → chat.json
weflow-agent import chat.json --name 张書源
weflow-agent distill
weflow-agent export buzz          # 产出 张書源.agent.json
weflow-agent blindtest             # 对拍校准，确认「像」
# 2. 拖入 buzz 桌面端 Import 即可
```

**文档要求**：README 带 10 分钟跑通 + 完整案例；每个子命令有 `--help`。

---

## 4. 架构（方案 A：单仓库 CLI）

```
weflow-agent/
├── pyproject.toml          # 打包配置（console_scripts 入口）
├── src/weflow_agent/
│   ├── cli/                # 命令入口（typer/click）
│   │   ├── __init__.py
│   │   ├── app.py          # 主入口，注册所有子命令
│   │   ├── import_cmd.py   # import：解析 WeFlow JSON
│   │   ├── distill_cmd.py  # distill：蒸馏引擎
│   │   ├── export_cmd.py   # export：skill → buzz 快照/pack
│   │   └── blindtest_cmd.py# blindtest：盲测对拍
│   ├── core/               # 蒸馏引擎（抽自 dot-skill）
│   │   ├── parser.py       # WeFlow JSON → 结构化消息
│   │   ├── persona.py      # 人物模型 + 记忆提取
│   │   ├── builder.py      # 生成 persona skill 文本
│   │   └── prompts/        # analyzer/builder 提示词
│   ├── buzz/               # buzz 适配层
│   │   ├── snapshot.py     # skill → .agent.json（v1 快照）
│   │   └── team.py         # 多 agent → persona pack + 订阅配置
│   └── quality/            # 质量关卡
│       └── blindtest.py    # 真实片段 vs agent 接话对拍
├── examples/               # 脱敏示例聊天 + 教程
├── tests/                  # 单元测试（示例数据）
└── docs/
    └── superpowers/specs/  # 设计文档
```

**模块边界**：
- `core/` 不 import `buzz/`，只产出中立的「人物档案」（PersonaDoc + Memory[]）
- `buzz/` 消费中立的 PersonaDoc，负责格式适配
- `cli/` 只做编排，无业务逻辑
- 每个模块可独立测试

---

## 5. 核心数据流

```
WeFlow JSON ──import──> 结构化消息（Message[]：双方/时间线/类型）
        │
        ├──distill──> PersonaDoc（表达硬规则 + 真实例句 + 性格层 + 记忆签名）
        │     └── 记忆提取：共同回忆/事实/偏好 → Memory[]
        │
        ├──export──> 张書源.agent.json（buzz-agent-snapshot v1，含 memory）
        └──deploy──> buzz pack（多 agent + subscribe/triggers 群组配置）

反馈环：
  真实聊天片段 ──blindtest──> agent 接话 ──对拍──> 相似度评分/人工确认
```

**中立的 PersonaDoc 结构**（core 的输出）：
```yaml
name: 张書源
display_name: 张書源
relationship: 高中+大学同学，好朋友
profile: { gender, age, mbti, tags, ... }
expression_rules:        # 表达硬规则（强制）
  - 一次只说一句话，单条 ≤15 字
  - 禁止书面语/完整长句/抒情总结
signature_phrases: [...]
example_replies: { 约饭: [...], 惊讶: [...], ... }
memory:                  # 记忆条目
  - slug: core/memorial  body: 2022疫情网课用AI写小说，五级天尊比九级天尊强
  - slug: core/memorial  body: 东门东餐楼梯口是约饭见面坐标
layers: { closeness, withdrawal, conflict, repair, boundaries }
```

---

## 6. CLI 接口

```text
weflow-agent init                     # 初始化工作目录 + 生成 config
weflow-agent import <chat.json> --name <名称> [--role friend|colleague|celebrity]
weflow-agent distill [--force]        # 生成/更新 persona
weflow-agent export buzz [--out DIR]  # 产出 .agent.json（单 agent）
weflow-agent export pack [--out DIR]  # 产出 buzz persona pack（多 agent 社群）
weflow-agent blindtest [--n 10]       # 盲测对拍（喂真实片段，agent 接话，评分）
weflow-agent list                     # 列出已蒸馏人物
```

幂等：每个命令可重复执行，覆盖式更新，不产生副作用（除写入产物目录）。

---

## 7. 关键设计决策（改进/增添点）

1. **蒸馏与 buzz 解耦**（中立的 PersonaDoc 中间格式）——不绑定单一平台
2. **记忆打包为一等能力**——distill 时从聊天提取共同回忆写入 Memory[]，export 时填入 `.agent.json` 的 `memory.entries`（buzz v1 快照支持，需 `memory.level=everything`）
3. **表达硬规则引擎内建**——张書源踩过的「文邹邹」坑对每个对象都会发生，builder 必须把「硬规则 + 真实例句」强制写入 prompt 顶层
4. **盲测对拍闭环**——`blindtest` 拿真实聊天当测试集，agent 接话，用户评分；不满足则触发 `distill --force` 迭代
5. **本地优先护栏**——默认零网络调用；export 时打印「产物含真实聊天内容，分享前请自行脱敏」提醒
6. **幂等可重跑**——每阶段输入输出文件化，方便调试和 CI

---

## 8. 错误处理与测试

**错误处理**：
- WeFlow JSON 格式不匹配 → 明确报错 + 提示去 `docs/WEFLOW_EXPORT.md` 看正确导出方式
- 蒸馏缺材料（无聊天、无手动信息）→ 提示并提供最小可跑方式
- 目标文件名冲突 → 覆盖前确认

**测试**：
- `tests/` 用 `examples/` 里的脱敏示例聊天（2-3 条短对话）跑通全流程
- 单元测试：parser / snapshot 生成 / pack 生成 / blindtest 评分
- 快照产物用 buzz 源码 schema 校验（`format/version/definition.name/displayName`）

---

## 9. 里程碑

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 最小闭环 | import + distill + export buzz 单 agent | 一条命令跑出 `.agent.json`，可导入 buzz |
| M2 记忆+盲测 | 记忆提取打包 + blindtest 对拍 | agent 带记忆，盲测可评分 |
| M3 社群 | export pack + 群组订阅配置 | 多 agent pack 可导入，群里能互动 |
| M4 GUI | 桌面/网页入口 | 非编程用户可上手 |

**当前进度**：M1 的核心逻辑已在手工验证（张書源 `.agent.json` 已生成且通过 schema 校验）。本次实现聚焦 M1 + M2。

---

## 10. 依赖

- **WeFlow**（外部）：微信聊天导出工具，产出 JSON。用户先自行导出。
- Python 3.10+，`typer` + `rich`（CLI），`pydantic`（模型），`pyyaml`（persona frontmatter）。
- 无网络依赖，纯本地。

---

*End of spec*
