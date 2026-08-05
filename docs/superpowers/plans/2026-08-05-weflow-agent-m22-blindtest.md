# weflow-agent M2.2 盲测对拍实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `weflow-agent blindtest` 命令：从已蒸馏人物解析的聊天记录里抽样真实对话片段，让蒸馏出的 agent（用蒸馏 prompt + 模型）接话，人工对比真实回复打分，输出评分汇总——把「像不像」从主观感受变成可验证的量化指标。

**Architecture:** `core/blindtest.py` 提供纯逻辑（样本抽取、调用模型接话、评分汇总），`cli/blindtest_cmd.py` 做 CLI 交互（typer + 逐条人工打分）。复用 `load_config`（distill）、persona 产物（`persona/{name}.md` 的 system_prompt）、`parsed/{name}.json` 的消息。

**Tech Stack:** Python 3.10+、typer、httpx（现有依赖，无新增）。

## Global Constraints

- 复用现有产物：`parsed/{name}.json`（Message[]）、`persona/{name}.md`（system_prompt）、`load_config`
- 盲测接话必须用模型（复用 distll 的 OpenAI-compatible 调用模式），无 key 时抛 `DistillError`（延续红线，不兜底）
- 人工评分：1-5 整数，逐条打分，最后输出平均分 + 每条明细
- 交互式 CLI 打分在 e2e 测试中用 monkeypatch `input` 模拟；核心逻辑（样本抽取、agent 接话、评分汇总）抽成可测纯函数
- 中文注释、snake_case；全量测试保持绿

---

### Task 1: 盲测核心逻辑（core/blindtest.py）

**Files:**
- Create: `src/weflow_agent/core/blindtest.py`
- Test: `tests/test_blindtest.py`

**Interfaces:**
- Consumes: `Message`、`load_config`、`DistillError`（distill 模块）
- Produces:
  - `extract_pairs(messages: list[Message], n: int, context_len: int = 3) -> list[dict]` — 抽 n 个「对方最后发言」的对话对，每个 `{"context": [Message...], "real_reply": Message}`
  - `ask_agent(context_msgs: list[Message], name: str, system_prompt: str, config: dict) -> str` — 调模型让 agent 以人物口吻接话（OpenAI-compatible）
  - `rate_pairs(pairs, agent_replies, ratings) -> dict` — 汇总平均分/条数

- [ ] **Step 1: 写失败测试**

```python
# tests/test_blindtest.py
from weflow_agent.core.parser import parse_messages
from weflow_agent.core.blindtest import extract_pairs, rate_pairs, ask_agent

def test_extract_pairs_takes_them_reply():
    msgs = parse_messages("examples/chat.txt")
    pairs = extract_pairs(msgs, n=2, context_len=2)
    assert len(pairs) == 2
    # real_reply 必须是对方的发言
    assert all(p["real_reply"].sender != "我" for p in pairs)
    assert all(len(p["context"]) <= 2 for p in pairs)

def test_rate_pairs_summary():
    pairs = [{"real_reply": "a"}, {"real_reply": "b"}]
    ratings = {0: 4, 1: 5}
    summary = rate_pairs(pairs, ["接话1", "接话2"], ratings)
    assert summary["count"] == 2
    assert summary["average"] == 4.5

def test_ask_agent_uses_model(monkeypatch):
    # mock httpx.post 返回模型接话
    import json as _json
    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": "走，吃饭"}}]}})()
    monkeypatch.setattr("weflow_agent.core.blindtest.httpx.post", fake_post)
    reply = ask_agent([], "张書源", "你是张書源。", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
    assert reply == "走，吃饭"
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_blindtest.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/core/blindtest.py
"""盲测对拍：从真实聊天抽样片段，让 agent 接话，人工评分验证蒸馏质量。"""
import json
import re

import httpx

from .models import Message
from .distill import load_config, DistillError

_SELF_ALIASES = ("我", "self", "me")


def extract_pairs(messages: list[Message], n: int, context_len: int = 3) -> list[dict]:
    """抽取 n 个对话对：context 为上文（对方+自己），real_reply 为对方最后发言。"""
    pairs: list[dict] = []
    for i, m in enumerate(messages):
        if m.sender in _SELF_ALIASES:
            continue
        if len(pairs) >= n:
            break
        ctx = messages[max(0, i - context_len):i]
        if ctx:
            pairs.append({"context": ctx, "real_reply": m})
    return pairs


def _fmt_context(context: list[Message]) -> str:
    return "\n".join(f"{m.sender}: {m.content}" for m in context)


def ask_agent(context_msgs: list[Message], name: str, system_prompt: str, config: dict) -> str:
    """用蒸馏出的 persona + 模型，让 agent 以 {name} 的口吻接话。"""
    model = config.get("model") or {}
    if not model.get("api_key"):
        raise DistillError("未配置模型 API key，请先配置 [model] api_key。")
    prompt = (
        f"{system_prompt}\n\n"
        f"下面是和你的对话上下文，请以 {name} 的口吻回复下一句，只说一句：\n\n"
        f"{_fmt_context(context_msgs)}\n"
    )
    resp = httpx.post(
        f"{model['base_url'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {model['api_key']}"},
        json={"model": model["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def rate_pairs(pairs: list[dict], agent_replies: list[str], ratings: dict[int, int]) -> dict:
    """汇总评分：返回条数、平均分、各条分数。"""
    scores = [ratings[i] for i in range(len(pairs)) if i in ratings]
    return {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "details": {str(i): ratings[i] for i in ratings},
    }
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_blindtest.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/core/blindtest.py tests/test_blindtest.py
git commit -m "feat: 盲测核心逻辑（样本抽取 + agent 接话 + 评分汇总）"
```

---

### Task 2: CLI blindtest 命令（人工打分交互）

**Files:**
- Create: `src/weflow_agent/cli/blindtest_cmd.py`
- Modify: `src/weflow_agent/cli/app.py`
- Test: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `extract_pairs`、`ask_agent`、`rate_pairs`（Task 1）、`parse_messages`、`load_config`
- Produces: `run_blindtest(name, workdir, config, n) -> None`（typer 命令 `blindtest`，逐条显示真实 vs agent 回复，input 打分）

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_cli_e2e.py`）

```python
def test_blindtest_command(monkeypatch, tmp_path):
    import json as _json
    from weflow_agent.core.blindtest import ask_agent as _aa
    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": "走，吃饭"}}]}})()
    monkeypatch.setattr("weflow_agent.core.blindtest.httpx.post", fake_post)
    monkeypatch.setattr("weflow_agent.cli.blindtest_cmd.input", lambda *a: "4")
    out = str(tmp_path)
    runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    r = runner.invoke(app, ["blindtest", "--name", "张書源", "--workdir", out, "--config", "cfg.toml", "--n", "1"])
    assert r.exit_code == 0, r.output
    assert "平均分" in r.output
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_cli_e2e.py -v`
Expected: FAIL（命令不存在）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/cli/blindtest_cmd.py
"""blindtest：盲测对拍（真实回复 vs agent 接话，人工打分）。"""
import json
from pathlib import Path

import typer

from ..core.models import Message
from ..core.parser import parse_messages
from ..core.distill import load_config
from ..core.blindtest import extract_pairs, ask_agent, rate_pairs


def run_blindtest(name: str, workdir: str, config: dict, n: int) -> None:
    parsed_path = Path(workdir) / f"{name}.json"
    if not parsed_path.exists():
        raise typer.BadParameter(f"未找到解析产物 {parsed_path}，请先运行 import")
    msgs = [Message(**m) for m in json.loads(parsed_path.read_text(encoding="utf-8"))]
    persona_path = Path(workdir) / "persona" / f"{name}.md"
    system_prompt = persona_path.read_text(encoding="utf-8") if persona_path.exists() else f"你是{name}。"

    pairs = extract_pairs(msgs, n=n)
    ratings: dict[int, int] = {}
    for i, pair in enumerate(pairs):
        typer.echo(f"\n--- 片段 {i + 1}/{len(pairs)} ---")
        for m in pair["context"]:
            typer.echo(f"  {m.sender}: {m.content}")
        typer.echo(f"  真实回复: {pair['real_reply'].content}")
        agent_reply = ask_agent(pair["context"], name, system_prompt, config)
        typer.echo(f"  agent 接话: {agent_reply}")
        while True:
            try:
                score = int(typer.prompt("相似度评分 (1-5)", type=int))
                if 1 <= score <= 5:
                    ratings[i] = score
                    break
                typer.echo("请输入 1-5 的整数。")
            except Exception:
                typer.echo("请输入 1-5 的整数。")

    summary = rate_pairs(pairs, ["agent接话"] * len(pairs), ratings)
    typer.echo(f"\n盲测完成：共 {summary['count']} 条，平均分 {summary['average']}/5")
```

```python
# src/weflow_agent/cli/app.py 追加：
from .blindtest_cmd import run_blindtest

@app.command("blindtest")
def blindtest_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件"),
    n: int = typer.Option(5, "--n", help="抽样片段数"),
):
    """盲测对拍：真实回复 vs agent 接话，人工评分。"""
    run_blindtest(name, workdir, load_config(config_path), n)
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_cli_e2e.py -v`；再 `python -m pytest -q`
Expected: PASS（e2e 新增 1；全量绿）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/cli/blindtest_cmd.py src/weflow_agent/cli/app.py tests/test_cli_e2e.py
git commit -m "feat: blindtest 命令（人工打分交互）"
```

---

### Task 3: 文档更新

**Files:**
- Modify: `README.md`

**Interfaces:** 无（纯文档）

- [ ] **Step 1: README 加 blindtest 说明**

```markdown
## 盲测验证（像不像）

`weflow-agent blindtest --name 张書源` 会从聊天记录抽真实片段，让蒸馏出的 agent 接话，你逐条打分（1-5），最后给出平均分——验证蒸馏质量，不满意就重新 distill 或调模型。

```bash
weflow-agent blindtest --name 张書源 --n 5
```
```

更新命令表加 `blindtest` 行。

- [ ] **Step 2: 验证**

Run: `python -m pytest -q` 全量绿

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: blindtest 盲测用法"
```

---

## 自评（Self-Review）

- **Spec 覆盖**：盲测目标（真实片段 + agent 接话 + 人工评分 + 汇总）→ Task 1 核心 + Task 2 CLI；无 key 报错 → `ask_agent` 抛 DistillError；复用产物约定 → Task 1/2 用 parsed/persona/load_config。
- **占位符扫描**：每步含真实代码，无 TBD。
- **类型一致性**：`extract_pairs`/`ask_agent`/`rate_pairs` 在 Task 1 定义、Task 2 消费；`run_blindtest(name, workdir, config, n)` 与 app.py 传入的 `load_config(config_path)` 一致；`Message` 模型往返（parsed json）沿用既有模式。
- **既有测试**：e2e 的 blindtest 用 monkeypatch input + mock httpx，不碰网络。
