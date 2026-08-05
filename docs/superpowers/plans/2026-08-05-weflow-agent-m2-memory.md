# weflow-agent M2.1 记忆打包实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让蒸馏出的 persona 自带「共同记忆」——LLM 从聊天提取的回忆条目被完整持久化并写入 buzz `.agent.json` 的 `memory.entries`，导入 buzz 后 agent 记得你们的共同回忆。

**Architecture:** 三个改动点：`buzz/snapshot.py` 根据 PersonaDoc.memory 决定快照 memory 段；`core/distill` 把完整 PersonaDoc（含 memory）持久化为 JSON；`export_cmd` 读回完整 PersonaDoc 而非只读 md。

**Tech Stack:** Python 3.10+，现有依赖（pydantic、typer）。

## Global Constraints

- `.agent.json` 必须符合 buzz-agent-snapshot v1：`format="buzz-agent-snapshot"`、`version=1`、`definition.name`/`profile.displayName` 非空
- buzz 记忆格式：`memory.level` ∈ {`none`,`core`,`everything`}；`entries[].slug` 必须为 `core` 或 `mem/` 前缀，`body` 为回忆文本；`level=none` 时 `entries` 必须为空（否则 buzz 导入端拒绝 malformed）
- 产物约定：distill 产出 `persona/{name}.json`（完整 PersonaDoc）与 `persona/{name}.md`（可读）；export 从 `persona/{name}.json` 恢复
- 中文注释、snake_case；测试 pytest 真实断言；全量测试保持绿

---

### Task 1: snapshot 支持 memory 段（M2.1）

**Files:**
- Modify: `src/weflow_agent/buzz/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `PersonaDoc.memory: list[dict]`（已有字段，`[{slug, body}]`）
- Produces: `build_snapshot(doc)` 的 memory 段正确；`validate_snapshot(snapshot)` 增加 memory 一致性 + slug 合法性校验

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_snapshot.py`）

```python
def test_snapshot_with_memory_uses_everything():
    doc = _doc()
    doc.memory = [{"slug": "core", "body": "2022 疫情网课一起用 AI 写小说"}]
    snap = build_snapshot(doc)
    assert snap["memory"]["level"] == "everything"
    assert snap["memory"]["entries"][0]["slug"] == "core"
    validate_snapshot(snap)

def test_snapshot_no_memory_stays_none():
    snap = build_snapshot(_doc())  # memory 为空
    assert snap["memory"]["level"] == "none"
    assert snap["memory"]["entries"] == []

def test_snapshot_rejects_level_none_with_entries():
    bad = build_snapshot(_doc())
    bad["memory"] = {"level": "none", "entries": [{"slug": "core", "body": "x"}]}
    try:
        validate_snapshot(bad)
        assert False, "应抛 ValueError"
    except ValueError:
        pass

def test_snapshot_rejects_invalid_slug():
    bad = build_snapshot(_doc())
    bad["memory"] = {"level": "everything", "entries": [{"slug": "random", "body": "x"}]}
    try:
        validate_snapshot(bad)
        assert False, "slug 必须是 core 或 mem/ 前缀，应抛 ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: FAIL（build_snapshot 仍硬编码 none / validate 无校验）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/buzz/snapshot.py 中：
import re

_MEMORY_LEVELS = ("none", "core", "everything")
_SLUG_RE = re.compile(r"^(core|mem/)")


def build_snapshot(doc: PersonaDoc) -> dict:
    """PersonaDoc → buzz v1 快照 dict（camelCase）。"""
    memory_entries = list(doc.memory) if doc.memory else []
    memory_level = "everything" if memory_entries else "none"
    return {
        ...  # 其余字段不变
        "memory": {
            "level": memory_level,
            "entries": memory_entries,
        },
    }


def validate_snapshot(snapshot: dict) -> None:
    """校验 v1 快照必填约束，不合法抛 ValueError。"""
    ...  # 现有 format/version/name/displayName 校验保留
    memory = snapshot.get("memory", {})
    level = memory.get("level", "none")
    if level not in _MEMORY_LEVELS:
        raise ValueError(f"memory.level 必须是 {_MEMORY_LEVELS} 之一")
    entries = memory.get("entries", [])
    if level == "none" and entries:
        raise ValueError("memory.level 为 none 时 entries 必须为空")
    for e in entries:
        slug = e.get("slug", "")
        if not _SLUG_RE.match(slug):
            raise ValueError(f"memory.entries[].slug 必须是 core 或 mem/ 前缀，收到: {slug!r}")
        if not str(e.get("body", "")).strip():
            raise ValueError("memory.entries[].body 不能为空")
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: PASS（原有 2 + 新增 4 = 6 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/buzz/snapshot.py tests/test_snapshot.py
git commit -m "feat: 快照支持 memory 段（level=everything + slug 校验）"
```

---

### Task 2: distill 持久化完整 PersonaDoc + prompt slug 引导（M2.1）

**Files:**
- Modify: `src/weflow_agent/core/prompt.py`
- Modify: `src/weflow_agent/cli/distill_cmd.py`
- Test: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `PersonaDoc`（含 memory）、`distill()`（已有）
- Produces: `distill_cmd` 额外写 `persona/{name}.json`（`PersonaDoc.model_dump_json(indent=2)`）；prompt 引导模型记忆 slug 用 `core` 或 `mem/*`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_cli_e2e.py`）

```python
def test_distill_persists_persona_json_with_memory(tmp_path):
    out = str(tmp_path)
    runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    r = runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out])
    assert r.exit_code == 0, r.output
    json_path = tmp_path / "persona" / "张書源.json"
    assert json_path.exists(), "distill 应持久化完整 PersonaDoc JSON"
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert "system_prompt" in doc and "memory" in doc  # 完整字段
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_cli_e2e.py -v`
Expected: FAIL（`persona/张書源.json` 不存在）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/core/prompt.py — DISTILL_PROMPT 中 memory 说明改为：
# - memory: 共同回忆条目列表 [{slug, body}]，slug 用 "core"（最重要的核心回忆）
#   或 "mem/回忆名"（如 "mem/寺庙还愿"），body 是回忆一句话（摘自聊天记录）
```

```python
# src/weflow_agent/cli/distill_cmd.py — distill_persona 里，写完 md 后再写 json：
    out = persona_dir / f"{name}.md"
    out.write_text(doc.system_prompt or doc.model_dump_json(indent=2), encoding="utf-8")
    # 持久化完整 PersonaDoc（含 memory），供 export 恢复
    json_path = persona_dir / f"{name}.json"
    json_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_cli_e2e.py -v`
Expected: PASS（新增 1 + 原有通过）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/core/prompt.py src/weflow_agent/cli/distill_cmd.py tests/test_cli_e2e.py
git commit -m "feat: distill 持久化完整 PersonaDoc（含 memory）+ prompt 记忆 slug 引导"
```

---

### Task 3: export 读回完整 PersonaDoc（含 memory）+ 端到端验证（M2.1）

**Files:**
- Modify: `src/weflow_agent/cli/export_cmd.py`
- Test: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `persona/{name}.json`（Task M2-2 产出）
- Produces: `export_cmd` 从 json 恢复 `PersonaDoc`（优先 json，缺失才退回 md 重建）；e2e 断言 `.agent.json` 的 memory 段

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_cli_e2e.py`）

```python
def test_e2e_export_includes_memory_when_present(tmp_path):
    out = str(tmp_path)
    runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out])
    # 手动注入一条记忆，模拟 LLM 蒸馏产出的记忆（规则兜底无记忆）
    p = tmp_path / "persona" / "张書源.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["memory"] = [{"slug": "mem/寺庙", "body": "跟妈妈去寺庙还愿"}]
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    r = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r.exit_code == 0, r.output
    snap = json.loads((tmp_path / "export" / "张書源.agent.json").read_text(encoding="utf-8"))
    assert snap["memory"]["level"] == "everything"
    assert snap["memory"]["entries"][0]["slug"] == "mem/寺庙"
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_cli_e2e.py -v`
Expected: FAIL（export 仍走 md 重建，无 memory）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/cli/export_cmd.py — export_buzz 改为优先读 json：
    import json as _json
    from ..core.models import PersonaDoc as _PersonaDoc

    json_path = Path(workdir) / "persona" / f"{name}.json"
    md_path = Path(workdir) / "persona" / f"{name}.md"
    if json_path.exists():
        # 优先从完整 PersonaDoc 恢复（含 memory）
        doc = _PersonaDoc.model_validate(_json.loads(json_path.read_text(encoding="utf-8")))
    elif md_path.exists():
        # 兼容旧产物：只有 md 时回退为仅 system_prompt
        doc = _PersonaDoc(name=name, display_name=name, system_prompt=md_path.read_text(encoding="utf-8"))
    else:
        raise typer.BadParameter(f"未找到 persona {md_path}，请先运行 distill")
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_cli_e2e.py -v`；再 `python -m pytest -q` 全量
Expected: PASS（e2e 新增 2 个；全量 19 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/cli/export_cmd.py tests/test_cli_e2e.py
git commit -m "feat: export 从完整 PersonaDoc 恢复，记忆进入 .agent.json"
```

---

## 自评（Self-Review）

- **Spec 覆盖**：M2.1 目标（记忆进 .agent.json）→ Task M2-1（snapshot memory 段）+ Task M2-2（持久化）+ Task M2-3（export 读回）。Global Constraints（slug core/mem/ 前缀、level=none+空 entries、一致性）→ Task M2-1 校验。产物约定（persona/{name}.json）→ Task M2-2/3。
- **占位符扫描**：无 TBD/TODO，每步含真实代码。
- **类型一致性**：`PersonaDoc.memory`（list[dict]）在 Task M2-1 被 snapshot 消费、M2-2 被 model_dump_json 序列化、M2-3 被 model_validate 恢复，签名一致；`build_snapshot(doc)` / `validate_snapshot(snapshot)` 签名不变，调用方（write_snapshot_json）无需改。

## 后续扩展（不在本次范围）

- **M2.2 blindtest**：真实聊天片段 → 调 agent 模型接话 → 相似度评分/人工确认
- **M3**：`export pack` 多 agent 社群 + 群组订阅配置
