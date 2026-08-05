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
    assert (tmp_path / "persona" / "张書源.md").exists()
    # export
    r3 = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "export" / "张書源.agent.json").exists()
    # 隐私提醒
    assert "脱敏" in r3.output


def test_distill_persists_persona_json_with_memory(tmp_path):
    out = str(tmp_path)
    runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    r = runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out])
    assert r.exit_code == 0, r.output
    json_path = tmp_path / "persona" / "张書源.json"
    assert json_path.exists(), "distill 应持久化完整 PersonaDoc JSON"
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert "system_prompt" in doc and "memory" in doc  # 完整字段
