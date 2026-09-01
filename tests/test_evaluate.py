"""Auto-evaluation 测试（mock LLM）。"""
import json

import pytest

from alchemy_hive.core.evaluate import auto_evaluate
from alchemy_hive.core.models import PersonaDoc


def _make_persona(tmp_path, name="小明"):
    doc = PersonaDoc(
        name=name, display_name=name,
        system_prompt="你是小明，一个活泼的朋友。",
        memories=[{"slug": "core", "body": "一起吃饭", "trigger": "约饭"}],
        example_replies={"约饭": ["走，吃食堂"]},
    )
    p = tmp_path / f"{name}.json"
    p.write_text(doc.model_dump_json(), encoding="utf-8")
    return str(p)


def _mock_llm(monkeypatch, agent_reply="走啊", judge_score=75):
    """mock LLM：persona 回复用 agent_reply，judge 评分用 judge_score。"""
    call_count = {"n": 0}

    def fake_post(*a, **k):
        call_count["n"] += 1
        body = k.get("json") or {}
        content = body.get("messages", [{}])[0].get("content", "")

        # judge prompt 包含 "评估专家" 关键词
        if "评估专家" in content:
            result = {
                "authenticity": 8, "consistency": 7,
                "expression": 8, "emotional_depth": 7,
                "overall": judge_score,
                "summary": "persona 质量不错，表达自然。",
                "suggestions": ["可以增加更多口头禅"],
            }
        else:
            result = agent_reply

        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)}}]},
        })()
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)


def test_auto_evaluate_returns_score(tmp_path, monkeypatch):
    path = _make_persona(tmp_path)
    _mock_llm(monkeypatch)
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}
    result = auto_evaluate(path, config, n_scenarios=3)
    assert "overall" in result
    assert result["overall"] > 0
    assert "test_results" in result
    assert len(result["test_results"]) == 3


def test_auto_evaluate_includes_test_results(tmp_path, monkeypatch):
    path = _make_persona(tmp_path)
    _mock_llm(monkeypatch, agent_reply="好的没问题")
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}
    result = auto_evaluate(path, config, n_scenarios=2)
    for tr in result["test_results"]:
        assert "scenario" in tr
        assert "reply" in tr


def test_auto_evaluate_graceful_on_llm_failure(tmp_path, monkeypatch):
    """LLM 调用失败时返回 0 分而非抛异常。"""
    def fake_post(*a, **k):
        from alchemy_hive.core.llm import LLMError
        raise LLMError("offline")
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    path = _make_persona(tmp_path)
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}
    result = auto_evaluate(path, config, n_scenarios=2)
    assert result["overall"] == 0
    assert "失败" in result["summary"]
