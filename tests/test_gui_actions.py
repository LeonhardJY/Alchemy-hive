"""GUI 动作管线的纯函数测试（mock LLM，不走真实网络）。"""
import json

import pytest

from alchemy_hive.gui.actions import run_pipeline
from alchemy_hive.core.distill import DistillError

MODEL_CONFIG = {"base_url": "http://x", "api_key": "k", "model": "m"}


@pytest.fixture
def mock_llm(monkeypatch):
    """mock alchemy_hive.core.distill.httpx.post，返回假 OpenAI 响应，绕过真实网络。

    返回捕获到的请求 kwargs（url/headers/json），供测试断言样本发往所配端点。
    """

    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
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

    monkeypatch.setattr("alchemy_hive.core.distill.httpx.post", fake_post)
    return captured


def _assert_request_matches_config(captured, cfg):
    """锁死"样本发往所配端点"：url/auth/model 必须与传入配置一致。"""
    url = captured["url"]
    assert url.startswith(cfg["base_url"]), url
    assert "/chat/completions" in url, url
    assert cfg["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == cfg["model"]


def test_gui_actions_pipeline(mock_llm, tmp_path, examples_dir):
    logs = run_pipeline(
        str(examples_dir / "chat.txt"),
        "张書源",
        MODEL_CONFIG,
        str(tmp_path),
    )
    assert any("import" in l for l in logs)
    assert any("distill" in l for l in logs)
    assert (tmp_path / "export" / "张書源.agent.json").exists()
    _assert_request_matches_config(mock_llm, MODEL_CONFIG)


def test_gui_actions_pipeline_writes_parsed_json(mock_llm, tmp_path, examples_dir):
    run_pipeline(
        str(examples_dir / "chat.txt"),
        "张書源",
        MODEL_CONFIG,
        str(tmp_path),
    )
    parsed_path = tmp_path / "parsed" / "张書源.json"
    assert parsed_path.exists(), "管线应把解析产物写入 parsed/{name}.json"
    msgs = json.loads(parsed_path.read_text(encoding="utf-8"))
    assert isinstance(msgs, list) and len(msgs) > 0
    assert "sender" in msgs[0] and "content" in msgs[0] and "timestamp" in msgs[0]


def test_gui_actions_no_key_raises(examples_dir, tmp_path):
    with pytest.raises(DistillError):
        run_pipeline(str(examples_dir / "chat.txt"), "张書源", {}, str(tmp_path))
