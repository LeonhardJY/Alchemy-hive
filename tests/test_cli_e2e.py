import json
import os
from typer.testing import CliRunner
from weflow_agent.cli.app import app

runner = CliRunner()

def _fake_llm(monkeypatch):
    """mock weflow_agent.core.distill.httpx.post，返回假 OpenAI 响应，绕过真实网络。"""
    import json as _json

    def fake_post(*a, **k):
        payload = {"display_name": "张書源", "relationship": "好朋友",
                   "expression_rules": ["一次只说一句话"], "system_prompt": "你是张書源。"}
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": _json.dumps(payload, ensure_ascii=False)}}]}})()

    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)


def _write_fake_cfg(tmp_path):
    """写一份指向假模型的 [model] 配置，使 distill 通过 api_key 校验。"""
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("[model]\nbase_url=\"http://x\"\napi_key=\"k\"\nmodel=\"m\"\n", encoding="utf-8")
    return str(cfg)


def test_e2e_full_pipeline(tmp_path, monkeypatch):
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    # import
    r1 = runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    assert r1.exit_code == 0, r1.output
    parsed = json.loads((tmp_path / "张書源.json").read_text(encoding="utf-8"))
    assert len(parsed) >= 2
    # distill（mock LLM，走假配置，绕过真实网络）
    r2 = runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out, "--config", cfg])
    assert r2.exit_code == 0, r2.output
    assert (tmp_path / "persona" / "张書源.md").exists()
    # export
    r3 = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "export" / "张書源.agent.json").exists()
    # 隐私提醒
    assert "脱敏" in r3.output


def test_distill_persists_persona_json_with_memory(tmp_path, monkeypatch):
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    r = runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out, "--config", cfg])
    assert r.exit_code == 0, r.output
    json_path = tmp_path / "persona" / "张書源.json"
    assert json_path.exists(), "distill 应持久化完整 PersonaDoc JSON"
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert "system_prompt" in doc and "memory" in doc  # 完整字段


def test_e2e_export_includes_memory_when_present(tmp_path, monkeypatch):
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    runner.invoke(app, ["import", "examples/chat.txt", "--name", "张書源", "--out-dir", out])
    runner.invoke(app, ["distill", "--name", "张書源", "--workdir", out, "--config", cfg])
    # 手动注入一条记忆，模拟 LLM 蒸馏产出的记忆（mock LLM 未返回记忆）
    p = tmp_path / "persona" / "张書源.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["memory"] = [{"slug": "mem/寺庙", "body": "跟妈妈去寺庙还愿"}]
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    r = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r.exit_code == 0, r.output
    snap = json.loads((tmp_path / "export" / "张書源.agent.json").read_text(encoding="utf-8"))
    assert snap["memory"]["level"] == "everything"
    assert snap["memory"]["entries"][0]["slug"] == "mem/寺庙"


def test_e2e_export_corrupt_json_reports_clear_error(tmp_path):
    out = str(tmp_path)
    # 构造损坏 json（主产物存在但非法）
    (tmp_path / "persona").mkdir(parents=True)
    (tmp_path / "persona" / "张書源.json").write_text("{invalid", encoding="utf-8")
    r = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r.exit_code != 0, r.output
    assert "损坏" in r.output
    assert "Traceback" not in r.output


def test_e2e_export_schema_mismatch_reports_clear_error(tmp_path):
    out = str(tmp_path)
    # json 合法但缺必填字段 → ValidationError，同样报损坏类错误
    (tmp_path / "persona").mkdir(parents=True)
    (tmp_path / "persona" / "张書源.json").write_text("{}", encoding="utf-8")
    r = runner.invoke(app, ["export", "--name", "张書源", "--workdir", out])
    assert r.exit_code != 0, r.output
    assert "损坏" in r.output
    assert "Traceback" not in r.output
