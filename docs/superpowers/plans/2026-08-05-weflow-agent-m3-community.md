# weflow-agent M3 社群 pack 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `weflow-agent export pack` 命令：把多个已蒸馏人物批量导出为多个 buzz `.agent.json` + 一个社群配置清单（群名建议、每个 agent 的订阅频道/触发词/摘要、建群步骤），让用户逐个导入 buzz 后按清单建群形成 agent 社群。

**Architecture:** `core/community.py` 提供纯逻辑（生成社群清单 dict）；`cli/export_cmd.py` 加 `pack` 子命令（批量调用 `write_snapshot_json` 生成每个 agent 的 `.agent.json` + 写 `community.json`）。复用现有 `_find_parsed`/`_safe_filename`/`write_snapshot_json`。

**Tech Stack:** Python 3.10+、现有依赖（typer、pydantic）。

## Global Constraints

- `export pack` 只对**已蒸馏**人物生效：`persona/{safe_name}.json` 必须存在，缺失则报错提示「先运行 import + distill」
- 批量生成 `.agent.json`（复用 `write_snapshot_json`，保持 buzz v1 schema + memory）
- 产出社群清单 `community.json`：群名建议、agent 列表（displayName/agentJson 路径/subscribe 建议/triggers/一句话摘要）、setup 步骤
- `subscribe`/`triggers` 是 buzz 群组引导建议（`.agent.json` 导入后需在 buzz UI 配置），清单里如实标注
- 中文注释、snake_case；全量测试保持绿（89 baseline）

---

### Task 1: 社群清单生成（core/community.py）

**Files:**
- Create: `src/weflow_agent/core/community.py`
- Test: `tests/test_community.py`

**Interfaces:**
- Consumes: 无（纯函数）
- Produces: `build_community(names: list[str], export_dir: str, channel: str = "#friends") -> dict` — 返回社群清单 dict（含 agents 列表、setup_steps）；`build_agents_manifest(names, export_dir) -> list[dict]` — 每个 agent 的 {name, displayName, agentJson, subscribe, triggers, summary}

- [ ] **Step 1: 写失败测试**

```python
# tests/test_community.py
from weflow_agent.core.community import build_community

def test_build_community_lists_agents():
    comm = build_community(["张書源", "张鹏博"], "build/export")
    assert comm["channel"] == "#friends"
    assert len(comm["agents"]) == 2
    assert comm["agents"][0]["displayName"] == "张書源"
    assert comm["agents"][0]["agentJson"] == "build/export/张書源.agent.json"
    assert comm["agents"][0]["subscribe"] == ["#friends"]
    assert "setup_steps" in comm and len(comm["setup_steps"]) >= 3

def test_build_community_triggers():
    comm = build_community(["张書源"], "build/export")
    assert "@张書源" in comm["agents"][0]["triggers"]
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_community.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/core/community.py
"""社群清单生成：把多个已蒸馏人物组织成 buzz 群组引导。"""
from ..core.safe import safe_filename


def build_agents_manifest(names: list[str], export_dir: str, channel: str = "#friends") -> list[dict]:
    """每个 agent 的社群条目：路径用 safe 名，subscribe/triggers 为群组建议。"""
    agents = []
    for name in names:
        safe = safe_filename(name)
        agents.append({
            "name": name,
            "displayName": name,
            "agentJson": f"{export_dir}/{safe}.agent.json",
            "subscribe": [channel],
            "triggers": [f"@{name}", name],
            "summary": "",  # 可选：后续从 persona 提取一句话
        })
    return agents


def build_community(names: list[str], export_dir: str, channel: str = "#friends") -> dict:
    """社群配置清单：群名建议、agent 列表、setup 步骤。"""
    return {
        "community": f"{channel.strip('#')} 群",
        "channel": channel,
        "agents": build_agents_manifest(names, export_dir, channel),
        "setup_steps": [
            f"1. 把 build/export/ 下的每个 .agent.json 拖入 buzz 桌面端 My Agents 导入",
            f"2. 在 buzz 新建频道 {channel} 并把以上 agent 加入",
            f"3. 在群里 @agent 的名字触发对话；subscribe/triggers 是建议，导入后可在 buzz UI 微调",
        ],
    }
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_community.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/core/community.py tests/test_community.py
git commit -m "feat: 社群清单生成（agents 清单 + setup 步骤）"
```

---

### Task 2: export pack 命令（批量导出）

**Files:**
- Modify: `src/weflow_agent/cli/export_cmd.py`（加 pack 逻辑）
- Modify: `src/weflow_agent/cli/app.py`（export 加 --pack 或子命令）
- Test: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: `build_community`（Task 1）、`_find_parsed`、`write_snapshot_json`、`_safe_filename`
- Produces: `export_pack(names: list[str], workdir: str, channel: str) -> str` — 批量写 .agent.json + community.json，返回 community.json 路径

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_cli_e2e.py`）

```python
def test_export_pack_generates_multiple_agents(tmp_path, monkeypatch):
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    for nm in ("张書源", "张鹏博"):
        r1 = runner.invoke(app, ["import", "examples/chat.txt", "--name", nm, "--out-dir", out])
        assert r1.exit_code == 0, r1.output
        r2 = runner.invoke(app, ["distill", "--name", nm, "--workdir", out, "--config", str(cfg)])
        assert r2.exit_code == 0, r2.output
    r3 = runner.invoke(app, ["export", "pack", "--names", "张書源,张鹏博", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "export" / "张書源.agent.json").exists()
    assert (tmp_path / "export" / "张鹏博.agent.json").exists()
    comm = json.loads((tmp_path / "export" / "community.json").read_text(encoding="utf-8"))
    assert len(comm["agents"]) == 2

def test_export_pack_missing_persona_errors(tmp_path):
    out = str(tmp_path)
    r = runner.invoke(app, ["export", "pack", "--names", "不存在的人", "--workdir", out])
    assert r.exit_code != 0
    assert "distill" in r.output
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_cli_e2e.py -v`
Expected: FAIL（pack 子命令不存在）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/cli/export_cmd.py 追加：
def export_pack(names: list[str], workdir: str, channel: str = "#friends") -> str:
    """批量导出多 agent 的 .agent.json + 社群清单 community.json。"""
    from ..core.community import build_community
    from ..core.models import PersonaDoc
    from ..buzz.snapshot import write_snapshot_json
    export_dir = Path(workdir) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        persona_path = Path(workdir) / "persona" / f"{_safe_filename(name)}.json"
        if not persona_path.exists():
            raise typer.BadParameter(
                f"未找到 {name} 的蒸馏产物 {persona_path}，请先运行 import + distill")
        doc = PersonaDoc.model_validate(json.loads(persona_path.read_text(encoding="utf-8")))
        write_snapshot_json(doc, str(export_dir))
    comm = build_community(names, str(export_dir), channel)
    comm_path = export_dir / "community.json"
    comm_path.write_text(json.dumps(comm, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"[export pack] 已生成 {len(names)} 个 agent + 社群清单 -> {comm_path}")
    return str(comm_path)
```

```python
# src/weflow_agent/cli/app.py 追加（export 下嵌套命令）：
@app.command("export")
def export_cmd(
    name: str = typer.Option(None, "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
):
    """导出 buzz .agent.json 快照。"""
    export_buzz(name, workdir)

@app.command("pack")
def pack_cmd(
    names: str = typer.Option(..., "--names", help="逗号分隔的人物名，如 张書源,张鹏博"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    channel: str = typer.Option("#friends", "--channel", help="群组频道名"),
):
    """批量导出多 agent 快照 + 社群清单。"""
    export_pack([n.strip() for n in names.split(",") if n.strip()], workdir, channel)
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_cli_e2e.py -v`；再 `python -m pytest -q`
Expected: PASS（e2e 新增 2；全量 91+ passed）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/cli/export_cmd.py src/weflow_agent/cli/app.py tests/test_cli_e2e.py
git commit -m "feat: export pack 批量导出社群（多 agent + 群组清单）"
```

---

### Task 3: 文档更新

**Files:**
- Modify: `README.md`

**Interfaces:** 无（纯文档）

- [ ] **Step 1: README 加社群一节**

```markdown
## 社群（多 agent）

把多个蒸馏出的人物批量导出，导入 buzz 后建群形成社群：

```bash
weflow-agent export pack --names 张書源,张鹏博
# 产出 build/export/张書源.agent.json、张鹏博.agent.json + community.json（群组清单）
```

按 `community.json` 的 setup 步骤：逐个把 `.agent.json` 拖入 buzz 导入 → 新建频道（默认 #friends）把 agent 加入 → 在群里 @agent 触发对话。
```

命令表加 `export pack` 行。

- [ ] **Step 2: 验证**

Run: `python -m pytest -q` 全量绿

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: 社群 export pack 用法"
```

---

## 自评（Self-Review）

- **Spec 覆盖**：M3 目标（多 .agent.json + 群组清单）→ Task 1 清单生成 + Task 2 批量导出；复用 buzz v1 快照 → `write_snapshot_json`；缺失人物报错 → Task 2；subscribe/triggers 如实标注为建议 → Task 1。
- **占位符扫描**：无 TBD，每步含真实代码。
- **类型一致性**：`build_community(names, export_dir, channel)` 在 Task 1 定义 Task 2 消费；`export_pack(names, workdir, channel)` 与 app.py pack 命令传入的 list/str 一致；`_safe_filename`/`_find_parsed` 复用既有。
- **既有测试**：e2e 的 pack 测试用 `_fake_llm`/`_write_fake_cfg` 既有 helper，不碰网络。
