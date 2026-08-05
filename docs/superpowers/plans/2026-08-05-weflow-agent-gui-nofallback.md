# weflow-agent 方向调整实现计划：移除规则兜底 + 桌面 GUI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 蒸馏必须走 LLM（配置 key），移除规则兜底；新增 Tkinter 桌面图形界面，让用户在上传聊天文件、填模型配置后一键完成 weflow→buzz 蒸馏通路。

**Architecture:** 两个改动组。①`core/distill.py` 移除 `_rule_fallback`，`distill()` 无 key 或 LLM 失败时抛 `DistillError`；②新增 `gui/` 模块（Tkinter，Python 标准库无新依赖），把「import→distill→export」抽成可测试的 `gui/actions.py`，`app.py` 加 `gui` 命令启动界面。

**Tech Stack:** Python 3.10+、Tkinter（标准库）、现有 typer/pydantic/httpx。

## Global Constraints

- 蒸馏强制需要 LLM key：`distill()` 在无 api_key 或 LLM 调用失败时抛 `DistillError`（中文错误提示），**绝不回退**到规则兜底
- 删除 `_rule_fallback` 和 `_HARD_RULES`；`_llm_distill` 保留但失败不再静默
- GUI 复用现有 `core`/`buzz` 业务逻辑（产物约定 build/parsed、build/persona、build/export 不变）；GUI 只是薄壳
- GUI 业务逻辑抽成 `gui/actions.py`（纯函数，可 pytest 测试）；Tk 窗口本身人工验证（无法自动化）
- 中文注释、snake_case；全量测试保持绿（移除兜底后需适配既有测试）

---

### Task 1: distill 强制 key，移除规则兜底

**Files:**
- Modify: `src/weflow_agent/core/distill.py`
- Test: `tests/test_distill.py`

**Interfaces:**
- Consumes: `Message`、`PersonaDoc`（已有）
- Produces: `class DistillError(RuntimeError)`；`distill(messages, name, config)` 无 key 或失败时抛 `DistillError`，成功返回 `PersonaDoc`

- [ ] **Step 1: 写失败测试**（改 `tests/test_distill.py`：删 `test_rule_fallback_produces_prompt`，把 `test_distill_no_api_key_uses_fallback` 改为抛错）

```python
def test_distill_no_api_key_raises():
    msgs = parse_messages("examples/chat.txt")
    try:
        distill(msgs, "张書源", {})  # 空配置 → 无 api_key
        assert False, "无 key 应抛 DistillError"
    except DistillError:
        pass

def test_distill_llm_failure_raises(monkeypatch):
    msgs = parse_messages("examples/chat.txt")
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    def fake_post(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)
    try:
        distill(msgs, "张書源", config)
        assert False, "LLM 失败应抛 DistillError"
    except DistillError:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_distill.py -v`
Expected: FAIL（现在无 key 走兜底不抛错）

- [ ] **Step 3: 实现**（改 `src/weflow_agent/core/distill.py`）

```python
class DistillError(RuntimeError):
    """蒸馏失败：缺少模型配置或 LLM 调用失败。"""


def distill(messages: list[Message], name: str, config: dict) -> PersonaDoc:
    """入口：LLM 蒸馏。无 api_key 或调用失败时抛 DistillError，绝不兜底。"""
    api_key = (config.get("model") or {}).get("api_key")
    if not api_key:
        raise DistillError(
            "未配置模型 API key。请配置 .weflow-agent/config.toml 的 [model] api_key，"
            "或使用 `weflow-agent gui` 在界面中填写。"
        )
    doc = _llm_distill(messages, name, config)
    if doc is None or not doc.system_prompt:
        raise DistillError("LLM 蒸馏失败，请检查 base_url/api_key/model 配置与网络连接。")
    return doc
```

同时删除 `_rule_fallback` 函数和 `_HARD_RULES` 常量（保留 `_llm_distill`、`load_config`、`_sample_text`）。

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_distill.py -v`
Expected: PASS（LLM mock 成功路径 + 2 个新报错测试通过；兜底测试已删）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/core/distill.py tests/test_distill.py
git commit -m "feat: distill 强制 LLM key，移除规则兜底"
```

---

### Task 2: e2e 适配（distill 步骤 mock LLM）

**Files:**
- Modify: `tests/test_cli_e2e.py`
- Modify: `src/weflow_agent/cli/distill_cmd.py`（支持传 config dict）

**Interfaces:**
- Consumes: `distill_persona(name, workdir, config)` 现收 config path；改为可收 dict 或 path
- Produces: e2e 的 distill 步骤注入 fake config + mock httpx，绕过真实网络

- [ ] **Step 1: 写失败测试**（改 `tests/test_cli_e2e.py`：distill 调用传 `--config` 指向 tmp 下的假 toml）

```python
def _fake_llm(monkeypatch):
    import json as _json
    def fake_post(*a, **k):
        payload = {"display_name": "张書源", "relationship": "好朋友",
                   "expression_rules": ["一次只说一句话"], "system_prompt": "你是张書源。"}
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": _json.dumps(payload, ensure_ascii=False)}}]}})()
    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)

def test_e2e_full_pipeline(tmp_path, monkeypatch):
    _fake_llm(monkeypatch)
    # 写假配置
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("[model]\nbase_url=\"http://x\"\napi_key=\"k\"\nmodel=\"m\"\n", encoding="utf-8")
    out = str(tmp_path)
    r1 = runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out, "--config", str(cfg)])
    assert r2.exit_code == 0, r2.output
    r3 = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "张書源.agent.json").exists()
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_cli_e2e.py -v`
Expected: FAIL（distill 无 key 现在抛错；或 distill_cmd 不接受 dict config）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/cli/distill_cmd.py — distill_persona 改为接受 config（dict 或 path）：
def distill_persona(name: str, workdir: str, config: dict | str | None) -> None:
    ...
    cfg = load_config(config) if isinstance(config, str) else (config or {})
    doc = distill(msgs, name, cfg)
    ...
```

```python
# src/weflow_agent/cli/app.py — distill 命令把 load_config 结果传入：
from ..core.distill import load_config
@app.command("distill")
def distill_cmd(name=..., workdir=..., config_path=...):
    distill_persona(name, workdir, load_config(config_path))
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_cli_e2e.py -v`；再 `python -m pytest -q`
Expected: PASS（全量保持绿，含 `test_e2e_export_includes_memory_when_present` 也需 mock LLM）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/cli/distill_cmd.py src/weflow_agent/cli/app.py tests/test_cli_e2e.py
git commit -m "test: e2e 蒸馏步骤 mock LLM，distill_cmd 支持 dict 配置"
```

---

### Task 3: GUI 业务动作（gui/actions.py）

**Files:**
- Create: `src/weflow_agent/gui/__init__.py`
- Create: `src/weflow_agent/gui/actions.py`
- Test: `tests/test_gui_actions.py`

**Interfaces:**
- Consumes: `parse_messages`、`distill`、`write_snapshot_json`（已有）
- Produces: `run_pipeline(chat_path, name, model_config, workdir) -> list[str]`（返回步骤日志，逐步执行 import→distill→export，含错误时抛 DistillError）

- [ ] **Step 1: 写失败测试**（mock LLM）

```python
def test_gui_actions_pipeline(mock_llm, tmp_path):
    logs = run_pipeline("examples/chat.txt", "张書源",
                        {"base_url": "http://x", "api_key": "k", "model": "m"}, str(tmp_path))
    assert any("import" in l for l in logs)
    assert any("distill" in l for l in logs)
    assert (tmp_path / "export" / "张書源.agent.json").exists()

def test_gui_actions_no_key_raises(tmp_path):
    try:
        run_pipeline("examples/chat.txt", "张書源", {}, str(tmp_path))
        assert False, "无 key 应抛 DistillError"
    except DistillError:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_gui_actions.py -v`
Expected: FAIL（actions 不存在）

- [ ] **Step 3: 实现**

```python
# src/weflow_agent/gui/actions.py
"""GUI 复用的蒸馏动作：把 import→distill→export 串成一个可测试的管线。"""
from pathlib import Path

from ..core.distill import distill, DistillError
from ..core.parser import parse_messages
from ..buzz.snapshot import write_snapshot_json


def run_pipeline(chat_path: str, name: str, model_config: dict, workdir: str) -> list[str]:
    """执行完整蒸馏管线，返回步骤日志。model_config 形如 {"base_url","api_key","model"}。"""
    logs: list[str] = []
    root = Path(workdir)

    parsed_dir = root / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    msgs = parse_messages(chat_path)
    logs.append(f"[import] 解析 {len(msgs)} 条消息")

    cfg = {"model": model_config}
    doc = distill(msgs, name, cfg)
    logs.append("[distill] 蒸馏完成")

    persona_dir = root / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / f"{name}.md").write_text(doc.system_prompt, encoding="utf-8")
    (persona_dir / f"{name}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    logs.append(f"[distill] 已写 persona/{name}.md + .json")

    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir))
    logs.append(f"[export] 已生成 {path}")
    logs.append("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")
    return logs
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_gui_actions.py -v`
Expected: PASS（2 passed，mock LLM 下管线跑通）

- [ ] **Step 5: Commit**

```bash
git add src/weflow_agent/gui/ tests/test_gui_actions.py
git commit -m "feat: GUI 蒸馏动作管线（actions）"
```

---

### Task 4: Tkinter 主窗口 + gui 命令

**Files:**
- Create: `src/weflow_agent/gui/app.py`（Tk 主窗口，薄壳）
- Modify: `src/weflow_agent/cli/app.py`（加 `gui` 命令）
- Test: 无（Tk 窗口无法自动化；靠 actions 测试 + 手工验证）

**Interfaces:**
- Consumes: `run_pipeline`（Task B1）
- Produces: `run_gui()` 启动 Tk 窗口；`weflow-agent gui` 命令入口

- [ ] **Step 1: 实现 Tk 窗口**（`src/weflow_agent/gui/app.py`）

```python
"""weflow-agent 桌面界面（Tkinter 薄壳，业务逻辑在 actions.py）。"""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .actions import run_pipeline
from ..core.distill import DistillError


class AgentGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("weflow-agent — 微信聊天 → buzz agent")
        root.geometry("640x560")
        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)

        # 聊天文件
        ttk.Label(frm, text="聊天文件（WeFlow 导出 JSON 或微信 txt）:").grid(row=0, column=0, sticky="w")
        self.chat_path = tk.StringVar()
        ttk.Entry(frm, textvariable=self.chat_path, width=40).grid(row=1, column=0, sticky="we")
        ttk.Button(frm, text="浏览…", command=self._pick_file).grid(row=1, column=1)

        # 人物名
        ttk.Label(frm, text="人物名（显示名）:").grid(row=2, column=0, sticky="w")
        self.name = tk.StringVar(value="张書源")
        ttk.Entry(frm, textvariable=self.name).grid(row=3, column=0, sticky="we")

        # 模型配置
        ttk.Label(frm, text="模型配置（LLM 必需）:").grid(row=4, column=0, sticky="w")
        ttk.Label(frm, text="base_url").grid(row=5, column=0, sticky="w")
        self.base_url = tk.StringVar(value="https://api.deepseek.com/v1")
        ttk.Entry(frm, textvariable=self.base_url).grid(row=6, column=0, sticky="we")
        ttk.Label(frm, text="api_key").grid(row=7, column=0, sticky="w")
        self.api_key = tk.StringVar()
        ttk.Entry(frm, textvariable=self.api_key, show="*").grid(row=8, column=0, sticky="we")
        ttk.Label(frm, text="model").grid(row=9, column=0, sticky="w")
        self.model = tk.StringVar(value="deepseek-chat")
        ttk.Entry(frm, textvariable=self.model).grid(row=10, column=0, sticky="we")

        # 运行按钮
        ttk.Button(frm, text="开始蒸馏（import → distill → export）", command=self._run).grid(row=11, column=0, columnspan=2, pady=8)

        # 日志区
        ttk.Label(frm, text="日志:").grid(row=12, column=0, sticky="w")
        self.log = scrolledtext.ScrolledText(frm, height=14, state="disabled", width=74)
        self.log.grid(row=13, column=0, columnspan=2, sticky="nsew")
        frm.rowconfigure(13, weight=1)
        frm.columnconfigure(0, weight=1)

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(title="选择聊天文件", filetypes=[("聊天文件", "*.json *.txt"), ("所有文件", "*.*")])
        if path:
            self.chat_path.set(path)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _run(self) -> None:
        model_config = {"base_url": self.base_url.get().strip(), "api_key": self.api_key.get().strip(), "model": self.model.get().strip()}
        try:
            logs = run_pipeline(self.chat_path.get().strip(), self.name.get().strip(), model_config, "build")
            for line in logs:
                self._append_log(line)
            self._append_log("完成 ✅ 可在 build/export/ 找到 .agent.json，拖入 buzz 桌面端导入。")
        except DistillError as e:
            self._append_log(f"错误: {e}")
            messagebox.showerror("蒸馏失败", str(e))
        except Exception as e:
            self._append_log(f"错误: {e}")
            messagebox.showerror("出错", str(e))


def run_gui() -> None:
    root = tk.Tk()
    AgentGUI(root)
    root.mainloop()
```

- [ ] **Step 2: 注册 gui 命令**（`src/weflow_agent/cli/app.py` 加）

```python
@app.command("gui")
def gui_cmd():
    """启动桌面图形界面。"""
    from ..gui.app import run_gui
    run_gui()
```

- [ ] **Step 3: 验证**

Run: `python -m pytest -q`（全量绿）；`weflow-agent --help` 显示 gui 命令；`weflow-agent gui` 能弹出窗口（人工验证，需真实显示环境）

- [ ] **Step 4: Commit**

```bash
git add src/weflow_agent/gui/app.py src/weflow_agent/cli/app.py
git commit -m "feat: Tkinter 桌面界面 + gui 命令"
```

---

### Task 5: 文档更新（GUI + 强制 key）

**Files:**
- Modify: `README.md`
- Modify: `docs/WEFLOW_EXPORT.md`（如需）

**Interfaces:** 无（纯文档）

- [ ] **Step 1: README 更新**
- 删掉「规则兜底」相关表述（快速上手、配置说明）
- 明确：蒸馏必须配置模型 key（GUI 或 config.toml），无 key 会报错
- 加「图形界面」一节：`weflow-agent gui` 启动，界面填写聊天文件/人物名/模型配置，一键蒸馏导出
- 更新「配置 LLM（必需）」段落：不再有"可选/兜底"

- [ ] **Step 2: 验证**

Run: `python -m pytest -q` 全量绿

- [ ] **Step 3: Commit**

```bash
git add README.md docs/WEFLOW_EXPORT.md
git commit -m "docs: 更新 GUI 用法 + 强制 LLM 配置说明"
```

---

## 自评（Self-Review）

- **Spec 覆盖**：移除兜底 → Task A1/A2；GUI → Task B1/B2；文档 → Task B3。Global Constraints（强制 key、删 _rule_fallback、GUI 薄壳、actions 可测）逐任务落实。
- **占位符扫描**：每步含真实代码，无 TBD。
- **类型一致性**：`distill(messages, name, config)` 签名不变；`run_pipeline` 在 B1 定义 B2 消费；`DistillError` A1 定义、A2/B1 引用；`distill_cmd` config 参数 A2 改为 dict|str，B 不受影响。
- **既有测试适配**：A2 处理了 e2e 里 distill 依赖兜底的测试；`test_distill_no_api_key_uses_fallback` 在 A1 已改；LLM mock 测试沿用 Task 4 的 fake response 模式。
