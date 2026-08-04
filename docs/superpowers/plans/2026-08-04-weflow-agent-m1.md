# weflow-agent M1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「WeFlow 微信聊天导出 JSON → 蒸馏成人物 persona → 导出 buzz `.agent.json`」做成一条命令可跑通的本地 CLI，让有编程基础的人快速上手。

**Architecture:** 单仓库 monorepo CLI（typer）。`core/` 负责解析与蒸馏，产出中立的 PersonaDoc；`buzz/` 消费 PersonaDoc 生成 `.agent.json` 快照；`cli/` 只编排。蒸馏默认走 LLM（OpenAI-compatible），无 API key 时规则兜底。

**Tech Stack:** Python 3.10+、typer、rich、pydantic、pyyaml、httpx。零网络依赖（除 LLM 蒸馏可选调用）。

## Global Constraints

- Python ≥ 3.10；依赖限：typer、rich、pydantic、pyyaml、httpx
- `.agent.json` 必须符合 buzz-agent-snapshot v1：`format="buzz-agent-snapshot"`、`version=1`、`definition.name` 非空、`profile.displayName` 非空
- 除用户显式配置 LLM 外，工具零网络调用；导出时打印「产物含真实聊天内容，分享前请自行脱敏」提醒
- 所有子命令幂等可重跑，覆盖式写产物
- 代码用中文注释（面向中文用户），命名用 snake_case（python 惯例）
- 每个任务结束有可独立运行的测试（`pytest`）

---

### Task 1: 项目脚手架 + CLI 骨架

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/weflow_agent/__init__.py`
- Create: `src/weflow_agent/cli/__init__.py`
- Create: `src/weflow_agent/cli/app.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `weflow-agent` 可执行入口；`app`（typer 实例）在 `src/weflow_agent/cli/app.py`，注册 `init/import/distill/export` 四个子命令占位。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli.py
from typer.testing import CliRunner
from weflow_agent.cli.app import app

runner = CliRunner()

def test_cli_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "weflow-agent" in result.output

def test_cli_import_subcommand_exists():
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL（`ModuleNotFoundError: weflow_agent`）

- [ ] **Step 3: 最小实现**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "weflow-agent"
version = "0.1.0"
description = "从 WeFlow 导出的微信聊天蒸馏人物 AI agent，一键导出 buzz .agent.json"
requires-python = ">=3.10"
dependencies = ["typer>=0.12", "rich>=13", "pydantic>=2.5", "pyyaml>=6", "httpx>=0.27"]

[project.scripts]
weflow-agent = "weflow_agent.cli.app:main"

[tool.setuptools.packages.find]
where = ["src"]
```

```gitignore
# .gitignore
__pycache__/
*.pyc
.venv/
dist/
build/
*.egg-info/
.pytest_cache/
.weflow-agent/
```

```python
# src/weflow_agent/__init__.py
"""weflow-agent: WeFlow 聊天记录 → 人物 AI agent → buzz。"""
__version__ = "0.1.0"
```

```python
# src/weflow_agent/cli/__init__.py
from .app import app, main
__all__ = ["app", "main"]
```

```python
# src/weflow_agent/cli/app.py
"""CLI 主入口：注册子命令。子命令实现见 import_cmd / distill_cmd / export_cmd。"""
from typing import Optional
import typer

app = typer.Typer(
    help="weflow-agent: 从微信聊天记录蒸馏人物 AI agent，导出 buzz 快照。",
    no_args_is_help=True,
)

@app.command()
def init(config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件路径")):
    """初始化工作目录，生成配置模板。"""
    typer.echo(f"[init] 配置模板将生成到 {config_path}（M1 占位）")

@app.command()
def import_chat(
    input_path: str = typer.Argument(..., help="WeFlow 导出的 JSON 或微信导出 txt"),
    name: str = typer.Option(..., "--name", help="人物名（显示名）"),
    out_dir: str = typer.Option("build/parsed", "--out-dir", help="解析结果输出目录"),
):
    """解析聊天记录 → 结构化消息。"""
    typer.echo(f"[import] 占位: {input_path} -> {name}")

@app.command()
def distill(
    name: str = typer.Option(..., "--name", help="人物名"),
    force: bool = typer.Option(False, "--force", help="强制重新蒸馏"),
):
    """蒸馏 PersonaDoc + persona skill。"""
    typer.echo(f"[distill] 占位: {name}")

@app.command()
def export(
    name: str = typer.Option(..., "--name", help="人物名"),
    out_dir: str = typer.Option("build/export", "--out-dir", help="导出目录"),
):
    """导出 buzz .agent.json 快照。"""
    typer.echo(f"[export] 占位: {name} -> {out_dir}")

def main() -> None:
    app()

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行验证通过**

Run:
```bash
pip install -e .
pytest tests/test_cli.py -v
```
Expected: PASS（2 passed）；`weflow-agent --help` 能打印子命令列表。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src/ tests/test_cli.py
git commit -m "chore: M1 项目脚手架与 CLI 骨架"
```

---

### Task 2: 消息解析（WeFlow JSON + 微信 txt）

**Files:**
- Create: `src/weflow_agent/core/__init__.py`
- Create: `src/weflow_agent/core/models.py`
- Create: `src/weflow_agent/core/parser.py`
- Create: `examples/chat.json`（脱敏示例）
- Create: `examples/chat.txt`（脱敏示例）
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: 无（纯函数）
- Produces:
  - `Message(sender: str, content: str, timestamp: str)` — pydantic 模型
  - `parse_messages(path: str) -> list[Message]` — 按扩展名分流 `.json`(WeFlow) / `.txt`(微信导出)，宽容探测字段名
  - `infer_direction(msg_sender: str, self_aliases: list[str]) -> "me" | "them"` — 判断双方

- [ ] **Step 1: 写失败测试**

```python
# tests/test_parser.py
from weflow_agent.core.parser import parse_messages
from weflow_agent.core.models import Message

def test_parse_weflow_json():
    msgs = parse_messages("examples/chat.json")
    assert len(msgs) >= 3
    assert all(isinstance(m, Message) for m in msgs)
    assert any(m.content == "epic又要送了？" for m in msgs)

def test_parse_wechat_txt():
    msgs = parse_messages("examples/chat.txt")
    assert len(msgs) >= 2
    assert msgs[0].sender == "张書源"

def test_parse_detects_direction():
    msgs = parse_messages("examples/chat.json")
    assert any(m.sender == "我" for m in msgs)
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 最小实现**

```python
# src/weflow_agent/core/models.py
"""中立数据模型：解析与蒸馏共用，不依赖任何平台。"""
from pydantic import BaseModel


class Message(BaseModel):
    """一条聊天消息。"""
    sender: str          # 发送者显示名，用户本人约定为 "我"
    content: str         # 文本内容（过滤图片/表情/链接等非文本占位后）
    timestamp: str       # "YYYY-MM-DD HH:MM:SS"


class PersonaDoc(BaseModel):
    """蒸馏产出的中立人物档案（M1 先支持字段，蒸馏任务再填充）。"""
    name: str
    display_name: str
    relationship: str = ""
    profile: dict = {}
    expression_rules: list[str] = []
    signature_phrases: list[str] = []
    example_replies: dict = {}   # {场景: [真实例句]}
    memory: list[dict] = []      # [{slug, body}]
    layers: dict = {}            # closeness/withdrawal/conflict/repair/boundaries
    system_prompt: str = ""      # 生成后的完整 persona prompt 文本
```

```python
# src/weflow_agent/core/parser.py
"""聊天记录解析：支持 WeFlow 导出 JSON 与微信导出 txt。宽容探测字段名。"""
import json
import re
from pathlib import Path

from .models import Message

# 发送方向探测键：WeFlow 常用 isSend=1 表示"我发的"
_DIRECTION_KEYS = ("isSend", "is_send", "sendType", "isSender")
_TEXT_KEYS = ("msgContent", "content", "text", "msg")
_TIME_KEYS = ("createTime", "dateTime", "time", "timestamp")
_SENDER_KEYS = ("senderUsername", "sender", "username", "nickName", "name")

_SELF_ALIASES = ("我", "self", "me")


def _probe(record: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        if k in record and record[k] is not None:
            return str(record[k])
    return ""


def _parse_json(path: Path) -> list[Message]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else raw.get("messages", raw.get("data", []))
    if not isinstance(records, list):
        raise ValueError("无法识别的 WeFlow JSON 结构：期望顶层数组或 {messages:[...]}")
    out: list[Message] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        content = _probe(rec, _TEXT_KEYS)
        if not content or content.startswith("["):  # 跳过图片/表情/链接等占位
            continue
        sender = _probe(rec, _SENDER_KEYS) or "unknown"
        # isSend=1 → 本人
        if any(k in rec for k in _DIRECTION_KEYS):
            try:
                if int(rec.get("isSend", rec.get("is_send", 0))):
                    sender = "我"
            except (TypeError, ValueError):
                pass
        ts = _probe(rec, _TIME_KEYS)
        out.append(Message(sender=sender, content=content, timestamp=ts))
    return out


_TIME_LINE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) '(.+?)'\s*$")


def _parse_txt(path: Path) -> list[Message]:
    out: list[Message] = []
    current_sender = "unknown"
    current_ts = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _TIME_LINE.match(line)
        if m:
            current_ts, current_sender = m.groups()
            continue
        if line.strip() and not line.startswith("["):
            out.append(Message(sender=current_sender, content=line.strip(), timestamp=current_ts))
    return out


def parse_messages(path: str) -> list[Message]:
    """按扩展名解析聊天文件。.json → WeFlow；.txt → 微信导出。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.suffix.lower() == ".json":
        return _parse_json(p)
    if p.suffix.lower() == ".txt":
        return _parse_txt(p)
    raise ValueError(f"不支持的文件类型: {p.suffix}（支持 .json / .txt）")
```

```json
# examples/chat.json（脱敏示例）
[
  {"isSend": 0, "senderUsername": "张書源", "createTime": "2023-07-24 09:29:09", "msgContent": "epic又要送了？"},
  {"isSend": 1, "senderUsername": "me", "createTime": "2023-07-24 09:29:12", "msgContent": "我看看"},
  {"isSend": 0, "senderUsername": "张書源", "createTime": "2023-07-24 09:30:01", "msgContent": "[色]"}
]
```

```text
# examples/chat.txt（脱敏示例）
2023-07-24 09:29:09 '张書源'
epic又要送了？
2023-07-24 09:31:53 '我'
[图片]
2023-07-24 09:32:15 '张書源'
是了
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_parser.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/core/ examples/ tests/test_parser.py
git commit -m "feat: 聊天解析（WeFlow JSON + 微信 txt）"
```

---

### Task 3: buzz `.agent.json` 快照导出

**Files:**
- Create: `src/weflow_agent/buzz/__init__.py`
- Create: `src/weflow_agent/buzz/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `PersonaDoc`（Task 2 定义）
- Produces: `build_snapshot(doc: PersonaDoc) -> dict`（符合 buzz-agent-snapshot v1）；`write_snapshot_json(doc, out_path)`；`validate_snapshot(snapshot: dict) -> None`（不合法则抛 ValueError）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_snapshot.py
from weflow_agent.core.models import PersonaDoc
from weflow_agent.buzz.snapshot import build_snapshot, validate_snapshot

def _doc() -> PersonaDoc:
    return PersonaDoc(
        name="张書源",
        display_name="张書源",
        system_prompt="你是张書源。\n一次只说一句话。",
    )

def test_snapshot_matches_v1_schema():
    snap = build_snapshot(_doc())
    assert snap["format"] == "buzz-agent-snapshot"
    assert snap["version"] == 1
    assert snap["definition"]["name"] == "张書源"
    assert snap["profile"]["displayName"] == "张書源"
    assert "张書源" in snap["definition"]["systemPrompt"]
    assert snap["memory"]["level"] == "none"
    validate_snapshot(snap)

def test_snapshot_rejects_empty_name():
    bad = build_snapshot(_doc())
    bad["definition"]["name"] = "  "
    try:
        validate_snapshot(bad)
        assert False, "应抛 ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_snapshot.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 最小实现**

```python
# src/weflow_agent/buzz/snapshot.py
"""buzz agent 快照（buzz-agent-snapshot v1）生成与校验。"""
import json
from pathlib import Path

from ..core.models import PersonaDoc

_FORMAT = "buzz-agent-snapshot"
_VERSION = 1


def build_snapshot(doc: PersonaDoc) -> dict:
    """PersonaDoc → buzz v1 快照 dict（camelCase）。"""
    return {
        "format": _FORMAT,
        "version": _VERSION,
        "definition": {
            "name": doc.display_name,
            "sourceIsBuiltin": False,
            "systemPrompt": doc.system_prompt,
            # model/provider 留空，导入后由用户或操作员默认决定
            "model": None,
            "provider": None,
            "runtime": None,
            "parallelism": None,
            "idleTimeoutSeconds": None,
            "maxTurnDurationSeconds": None,
        },
        "profile": {
            "displayName": doc.display_name,
            "about": doc.relationship or None,
            "avatarDataUrl": None,
            "avatarUrl": None,
        },
        "memory": {
            "level": "none",
            "entries": [],
        },
    }


def validate_snapshot(snapshot: dict) -> None:
    """校验 v1 快照必填约束，不合法抛 ValueError。"""
    if snapshot.get("format") != _FORMAT:
        raise ValueError(f"format 必须为 {_FORMAT}")
    if snapshot.get("version") != _VERSION:
        raise ValueError(f"version 必须为 {_VERSION}")
    if not snapshot["definition"]["name"].strip():
        raise ValueError("definition.name 不能为空")
    if not snapshot["profile"]["displayName"].strip():
        raise ValueError("profile.displayName 不能为空")


def write_snapshot_json(doc: PersonaDoc, out_path: str) -> str:
    """写 .agent.json 并返回文件路径。文件名：{displayName}.agent.json。"""
    snap = build_snapshot(doc)
    validate_snapshot(snap)
    p = Path(out_path) / f"{doc.display_name}.agent.json"
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_snapshot.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/buzz/ tests/test_snapshot.py
git commit -m "feat: buzz .agent.json 快照生成与校验"
```

---

### Task 4: 蒸馏引擎（LLM + 规则兜底）

**Files:**
- Create: `src/weflow_agent/core/distill.py`
- Create: `src/weflow_agent/core/prompt.py`（内置蒸馏 prompt）
- Test: `tests/test_distill.py`

**Interfaces:**
- Consumes: `parse_messages`、`PersonaDoc`（Task 2）
- Produces:
  - `load_config(path: str | None) -> dict`（读 toml 配置；无则空 dict）
  - `distill(messages: list[Message], name: str, config: dict) -> PersonaDoc`
  - `_rule_fallback(messages, name) -> PersonaDoc`（无 API key 时纯规则兜底：统计高频词/长度，生成基础 prompt）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_distill.py
from weflow_agent.core.parser import parse_messages
from weflow_agent.core.distill import distill, _rule_fallback

def test_rule_fallback_produces_prompt():
    msgs = parse_messages("examples/chat.txt")
    doc = _rule_fallback(msgs, "张書源")
    assert doc.display_name == "张書源"
    assert "张書源" in doc.system_prompt
    assert "一次只说一句话" in doc.system_prompt  # 硬规则兜底必含

def test_distill_no_api_key_uses_fallback():
    msgs = parse_messages("examples/chat.txt")
    doc = distill(msgs, "张書源", {})  # 空配置 → 无 api_key → 规则兜底
    assert doc.system_prompt
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_distill.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 最小实现**

```python
# src/weflow_agent/core/prompt.py
"""内置蒸馏 prompt 模板：要求模型从聊天记录提取表达规则与真实例句。"""

DISTILL_PROMPT = """你是一个对话风格分析师。下面是两个人的微信聊天记录。
请分析 {name} 这个人，输出一个 JSON，字段如下：
- display_name: {name}
- relationship: 一句话描述他与对话对象的关系
- expression_rules: 3-5 条表达硬规则（如"一次只说一句话""禁用书面语"）
- signature_phrases: 高频口头禅/语气词列表
- example_replies: 一个对象，键是场景（约饭/惊讶/状态不好/给建议），值是真实聊天原话列表（必须摘自聊天记录，不要编造）
- memory: 共同回忆条目列表 [{slug, body}]，slug 用 "mem/{序号}"，body 是回忆一句话

要求：
1. 例句必须直接引用聊天记录原话。
2. 表达规则要能防止 AI 输出书面语。
3. 只输出 JSON，不要其它文字。

聊天记录：
{chat_sample}
"""
```

```python
# src/weflow_agent/core/distill.py
"""蒸馏引擎：LLM（OpenAI-compatible）优先，无 key 时规则兜底。"""
import json
import re
from collections import Counter

import httpx

from .models import Message, PersonaDoc
from .prompt import DISTILL_PROMPT

_SELF_ALIASES = ("我", "self", "me")
_HARD_RULES = [
    "一次只说一句话，发完等对方回复；可以连发但每条都是碎片",
    "单条消息尽量短，多用单字和短语（走/6/蛤/是了/卧槽）",
    "禁止书面语和完整长句，禁止比喻、排比、总结、抒情",
    "口语语气直接丢出来（蛤/嗷/emmm），不需要每句都有标点",
]


def load_config(path: str | None) -> dict:
    """读 toml 配置；无文件返回空 dict。支持 .weflow-agent/config.toml。"""
    if not path:
        return {}
    from pathlib import Path
    try:
        import tomllib  # py3.11+
    except ModuleNotFoundError:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _sample_text(messages: list[Message], limit: int = 200) -> str:
    return "\n".join(f"{m.timestamp} {m.sender}: {m.content[:80]}" for m in messages[:limit])


def _llm_distill(messages: list[Message], name: str, config: dict) -> PersonaDoc | None:
    """调 OpenAI-compatible 接口蒸馏；失败返回 None（由调用方兜底）。"""
    model = (config.get("model") or {}).get("base_url"), (config.get("model") or {}).get("api_key"), (config.get("model") or {}).get("model")
    base_url, api_key, model_name = model
    if not api_key:
        return None
    prompt = DISTILL_PROMPT.replace("{name}", name).replace("{chat_sample}", _sample_text(messages))
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        payload = json.loads(re.sub(r"```(json)?|```", "", content).strip())
        return PersonaDoc(name=name, display_name=name, **{k: v for k, v in payload.items() if k in PersonaDoc.model_fields})
    except Exception:
        return None


def _rule_fallback(messages: list[Message], name: str) -> PersonaDoc:
    """无 LLM 时规则兜底：统计对方高频词，生成基础 prompt。"""
    theirs = [m.content for m in messages if m.sender not in _SELF_ALIASES]
    words = [w for t in theirs for w in re.findall(r"[一-鿿]{1,4}", t)]
    top = [w for w, _ in Counter(words).most_common(8) if len(w) >= 2][:6]
    examples = [t[:40] for t in theirs if 2 <= len(t) <= 20][:5]
    prompt_lines = [
        f"你是{name}，以下是聊天记录提炼出的人物提示词。",
        "",
        "# 表达硬规则（必须遵守）",
        *[f"- {r}" for r in _HARD_RULES],
        "",
        "# 高频词",
        *[f"- {w}" for w in top],
        "",
        "# 参考例句（摘自聊天记录）",
        *[f"- {e}" for e in examples],
    ]
    return PersonaDoc(
        name=name,
        display_name=name,
        expression_rules=_HARD_RULES,
        signature_phrases=top,
        system_prompt="\n".join(prompt_lines),
    )


def distill(messages: list[Message], name: str, config: dict) -> PersonaDoc:
    """入口：LLM 蒸馏，失败或无 key 时规则兜底。"""
    doc = _llm_distill(messages, name, config)
    if doc is not None and doc.system_prompt:
        return doc
    return _rule_fallback(messages, name)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_distill.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/core/distill.py src/weflow_agent/core/prompt.py tests/test_distill.py
git commit -m "feat: 蒸馏引擎（LLM 优先 + 规则兜底）"
```

---

### Task 5: CLI 子命令串通（import/distill/export）

**Files:**
- Modify: `src/weflow_agent/cli/app.py`（把三个占位命令替换为真实实现）
- Create: `src/weflow_agent/cli/import_cmd.py`
- Create: `src/weflow_agent/cli/distill_cmd.py`
- Create: `src/weflow_agent/cli/export_cmd.py`
- Test: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `parse_messages`、`distill`、`load_config`、`write_snapshot_json`（Task 2-4）
- Produces: 端到端命令：`import <文件> --name X` → `distill --name X` → `export --name X` 产出 `<X>.agent.json`
- 产物约定：解析中间产物 `build/parsed/{name}.json`（list[Message]）；skill 文本 `build/persona/{name}.md`；快照 `build/export/{name}.agent.json`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli_e2e.py
import json
import os
from typer.testing import CliRunner
from weflow_agent.cli.app import app

runner = CliRunner()

def test_e2e_full_pipeline(tmp_path):
    out = str(tmp_path)
    # import
    r1 = runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    assert r1.exit_code == 0, r1.output
    parsed = json.loads((tmp_path / "张書源.json").read_text(encoding="utf-8"))
    assert len(parsed) >= 2
    # distill（无 api_key → 规则兜底）
    r2 = runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out])
    assert r2.exit_code == 0, r2.output
    assert (tmp_path / "张書源.md").exists()
    # export
    r3 = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "张書源.agent.json").exists()
    # 隐私提醒
    assert "脱敏" in r3.output
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/test_cli_e2e.py -v`
Expected: FAIL（命令未实现）

- [ ] **Step 3: 最小实现**

```python
# src/weflow_agent/cli/import_cmd.py
"""import：解析聊天记录 → 结构化消息中间产物。"""
import json
from pathlib import Path

import typer

from ..core.parser import parse_messages


def import_chat(input_path: str, name: str, out_dir: str) -> None:
    msgs = parse_messages(input_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"{name}.json"
    out.write_text(json.dumps([m.model_dump() for m in msgs], ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"[import] 解析 {len(msgs)} 条消息 -> {out}")
```

```python
# src/weflow_agent/cli/distill_cmd.py
"""distill：解析中间产物 → PersonaDoc → persona skill 文本。"""
import json
from pathlib import Path

import typer

from ..core.distill import distill, load_config
from ..core.models import Message


def distill_persona(name: str, workdir: str, config_path: str | None) -> None:
    parsed_path = Path(workdir) / f"{name}.json"
    if not parsed_path.exists():
        raise typer.BadParameter(f"未找到解析产物 {parsed_path}，请先运行 import")
    msgs = [Message(**m) for m in json.loads(parsed_path.read_text(encoding="utf-8"))]
    config = load_config(config_path)
    doc = distill(msgs, name, config)
    persona_dir = Path(workdir) / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    out = persona_dir / f"{name}.md"
    out.write_text(doc.system_prompt or doc.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"[distill] 已生成 persona -> {out}")
```

```python
# src/weflow_agent/cli/export_cmd.py
"""export：PersonaDoc → buzz .agent.json。"""
import json
from pathlib import Path

import typer

from ..buzz.snapshot import write_snapshot_json
from ..core.models import PersonaDoc


def export_buzz(name: str, workdir: str) -> None:
    persona_path = Path(workdir) / "persona" / f"{name}.md"
    if not persona_path.exists():
        raise typer.BadParameter(f"未找到 persona {persona_path}，请先运行 distill")
    doc = PersonaDoc(name=name, display_name=name, system_prompt=persona_path.read_text(encoding="utf-8"))
    export_dir = Path(workdir) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir))
    typer.echo(f"[export] 已生成 -> {path}")
    typer.echo("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")
```

```python
# src/weflow_agent/cli/app.py —— 替换三个占位命令为：
from .import_cmd import import_chat
from .distill_cmd import distill_persona
from .export_cmd import export_buzz

@app.command("import")
def import_cmd(
    input_path: str = typer.Argument(..., help="WeFlow 导出 JSON 或微信 txt"),
    name: str = typer.Option(..., "--name", help="人物名"),
    out_dir: str = typer.Option("build/parsed", "--out-dir", help="解析产物目录"),
):
    """解析聊天记录 → 结构化消息。"""
    import_chat(input_path, name, out_dir)

@app.command("distill")
def distill_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件"),
):
    """蒸馏 PersonaDoc + persona skill。"""
    distill_persona(name, workdir, config_path)

@app.command("export")
def export_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
):
    """导出 buzz .agent.json 快照。"""
    export_buzz(name, workdir)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/test_cli_e2e.py -v`
Expected: PASS（1 passed，端到端全流程跑通）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/cli/ tests/test_cli_e2e.py
git commit -m "feat: CLI 端到端闭环（import/distill/export）"
```

---

### Task 6: 文档（README + WeFlow 导出指南）

**Files:**
- Create: `README.md`
- Create: `docs/WEFLOW_EXPORT.md`
- Create: `.weflow-agent/config.toml.example`

**Interfaces:** 无（纯文档）

- [ ] **Step 1: 写 README**

```markdown
# weflow-agent

从 WeFlow 导出的微信聊天记录蒸馏出「人物 AI agent」，一键导出为 buzz `.agent.json`，拖进 Buzz 桌面端即可导入。本地优先，数据不出本机。

## 快速上手（10 分钟）

前置：Python 3.10+；用 [WeFlow](https://github.com/hicccc77/WeFlow) 导出私聊 JSON（见 [docs/WEFLOW_EXPORT.md](docs/WEFLOW_EXPORT.md)）。

```bash
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

产物含真实聊天内容。**分享到 GitHub 或发给他人前请自行脱敏**（替换姓名/号码）。工具本身零网络调用。
```

- [ ] **Step 2: 写 WeFlow 导出指南**

```markdown
# 用 WeFlow 导出微信聊天记录

1. 下载 [WeFlow](https://github.com/hicccc77/WeFlow) 并安装
2. 打开 WeFlow，用微信扫码登录
3. 选择要导出的私聊会话 → 导出为 JSON（选择「包含双方消息」）
4. 得到一个 `.json` 文件，即可作为 `weflow-agent import` 的输入

## 支持的文件格式

- **WeFlow 导出 JSON**：顶层数组或 `{messages:[...]}`；字段兼容 `msgContent/content/text`、`isSend/senderUsername` 等常见命名
- **微信导出 TXT**：`时间戳 '发送者'` + 内容 的多行格式
```

- [ ] **Step 3: 写配置模板**

```toml
# .weflow-agent/config.toml.example
# 复制为 .weflow-agent/config.toml 并填入你的模型配置
[model]
base_url = "https://api.deepseek.com/v1"
api_key = ""
model = "deepseek-chat"
```

- [ ] **Step 4: 运行验证**

Run: `weflow-agent --help`，确认三个子命令说明完整；`pip install -e . && pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add README.md docs/ .weflow-agent/
git commit -m "docs: README 快速上手 + WeFlow 导出指南"
```

---

## 自评（Self-Review）

**Spec 覆盖**：spec §5 数据流（import/distill/export）→ Task 2/4/5；§7 决策点 1 解耦（PersonaDoc）→ Task 2 models；决策点 3 硬规则 → Task 4 `_HARD_RULES`；决策点 5 本地护栏 + 脱敏提醒 → Task 5/6；§8 测试 → 每 Task；§10 依赖 → Task 1。记忆（决策点 2）与盲测（决策点 4）属 M2，计划末尾标注为后续，不在 M1 范围。

**占位符扫描**：无 TBD/TODO；每步含真实代码。`example_replies` 在 LLM 分支被模型填充、规则兜底留空——不影响 M1 跑通。

**类型一致性**：`PersonaDoc` 字段在 Task 2 models 定义，Task 3/4 按同名使用；`build_snapshot(doc)` / `distill(messages, name, config)` / `parse_messages(path)` 签名跨任务一致。

## 后续扩展（不在本次范围）

- **M2**：记忆打包（buzz engram slug 需对齐 `CORE_SLUG`，实现期查 buzz 源码）+ `blindtest` 盲测对拍
- **M3**：`export pack` 多 agent 社群 + 群组订阅配置
- **M4**：GUI
