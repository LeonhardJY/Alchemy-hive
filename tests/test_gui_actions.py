"""GUI 动作管线的纯函数测试（mock LLM，不走真实网络）。"""
import json

import pytest

from weflow_agent.gui.actions import run_pipeline
from weflow_agent.core.distill import DistillError


@pytest.fixture
def mock_llm(monkeypatch):
    """mock weflow_agent.core.distill.httpx.post，返回假 OpenAI 响应，绕过真实网络。"""

    def fake_post(*a, **k):
        payload = {
            "display_name": "张書源",
            "relationship": "好朋友",
            "expression_rules": ["一次只说一句话"],
            "system_prompt": "你是张書源。",
        }
        return type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {
                    "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]
                },
            },
        )()

    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)


def test_gui_actions_pipeline(mock_llm, tmp_path):
    logs = run_pipeline(
        "examples/chat.txt",
        "张書源",
        {"base_url": "http://x", "api_key": "k", "model": "m"},
        str(tmp_path),
    )
    assert any("import" in l for l in logs)
    assert any("distill" in l for l in logs)
    assert (tmp_path / "export" / "张書源.agent.json").exists()


def test_gui_actions_pipeline_writes_parsed_json(mock_llm, tmp_path):
    run_pipeline(
        "examples/chat.txt",
        "张書源",
        {"base_url": "http://x", "api_key": "k", "model": "m"},
        str(tmp_path),
    )
    parsed_path = tmp_path / "parsed" / "张書源.json"
    assert parsed_path.exists(), "管线应把解析产物写入 parsed/{name}.json"
    msgs = json.loads(parsed_path.read_text(encoding="utf-8"))
    assert isinstance(msgs, list) and len(msgs) > 0
    assert "sender" in msgs[0] and "content" in msgs[0] and "timestamp" in msgs[0]


def test_gui_actions_no_key_raises(tmp_path):
    try:
        run_pipeline("examples/chat.txt", "张書源", {}, str(tmp_path))
        assert False, "无 key 应抛 DistillError"
    except DistillError:
        pass
