import pytest

from weflow_agent.core.parser import parse_messages
from weflow_agent.core.distill import DistillError
from weflow_agent.core.blindtest import extract_pairs, rate_pairs, ask_agent


def test_extract_pairs_takes_them_reply():
    msgs = parse_messages("examples/chat.txt")
    pairs = extract_pairs(msgs, n=2, context_len=2)
    assert len(pairs) == 1
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


def test_ask_agent_missing_config_raises_distill_error():
    # 缺 base_url / 缺 model / 全缺（空配置）都应抛 DistillError，而非 KeyError 裸异常
    with pytest.raises(DistillError):
        ask_agent([], "张書源", "你是张書源。", {"model": {"api_key": "k", "model": "m"}})
    with pytest.raises(DistillError):
        ask_agent([], "张書源", "你是张書源。", {"model": {"base_url": "http://x", "api_key": "k"}})
    with pytest.raises(DistillError):
        ask_agent([], "张書源", "你是张書源。", {})


def test_ask_agent_network_error_raises_distill_error(monkeypatch):
    # httpx.post 抛 ConnectError（httpx.HTTPError 子类）→ 转 DistillError
    import httpx

    def raise_connect(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("weflow_agent.core.blindtest.httpx.post", raise_connect)
    with pytest.raises(DistillError):
        ask_agent([], "张書源", "你是张書源。", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})


def test_ask_agent_parse_error_raises_distill_error(monkeypatch):
    # 响应 JSON 无法解析（JSONDecodeError，ValueError 子类）→ 转 DistillError
    import json as _json

    def bad_json(self):
        raise _json.JSONDecodeError("Expecting value", "{bad", 0)

    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None, "json": bad_json})()

    monkeypatch.setattr("weflow_agent.core.blindtest.httpx.post", fake_post)
    with pytest.raises(DistillError):
        ask_agent([], "张書源", "你是张書源。", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
