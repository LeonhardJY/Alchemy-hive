import httpx
import pytest

from alchemy_hive.core.parser import parse_messages
from alchemy_hive.core.distill import DistillError
from alchemy_hive.core.blindtest import extract_pairs, rate_pairs, ask_agent


_CONFIG = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

_DEFAULT_CONTENT = object()  # 哨兵：区分"未传"与"显式传 None（content: null）"


def _ok_resp(content=_DEFAULT_CONTENT):
    """构造返回给定 content 的假响应（默认一段接话；content=None 模拟 DeepSeek content: null）。"""
    if content is _DEFAULT_CONTENT:
        content = "走，吃饭"
    return type(
        "R",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": content}}]},
        },
    )()


def test_extract_pairs_takes_them_reply(examples_dir):
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    pairs = extract_pairs(msgs, n=2, context_len=2)
    assert len(pairs) == 1
    # real_reply 必须是对方的发言
    assert all(p["real_reply"].sender != "我" for p in pairs)
    assert all(len(p["context"]) <= 2 for p in pairs)


def test_extract_pairs_zero_n_returns_empty(examples_dir):
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    assert extract_pairs(msgs, n=0) == []


def test_extract_pairs_empty_messages_returns_empty():
    assert extract_pairs([], n=5) == []


def test_rate_pairs_summary():
    pairs = [{"real_reply": "a"}, {"real_reply": "b"}]
    ratings = {0: 4, 1: 5}
    summary = rate_pairs(pairs, ["接话1", "接话2"], ratings)
    assert summary["count"] == 2
    assert summary["average"] == 4.5


def test_ask_agent_uses_model(monkeypatch):
    # mock httpx.post 返回模型接话，并锁死请求发往所配端点
    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        return _ok_resp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    reply = ask_agent([], "小明", "你是小明。", _CONFIG)
    assert reply == "走，吃饭"
    url = captured["url"]
    assert url.startswith(_CONFIG["model"]["base_url"]), url
    assert "/chat/completions" in url, url
    assert _CONFIG["model"]["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == _CONFIG["model"]["model"]


def test_ask_agent_null_content_returns_empty(monkeypatch):
    # DeepSeek 推理模型部分响应 content: null → 返回空串，绝不裸 AttributeError
    def fake_post(*a, **k):
        return _ok_resp(content=None)

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    assert ask_agent([], "小明", "你是小明。", _CONFIG) == ""


def test_ask_agent_non_str_content_coerced(monkeypatch):
    # content 为数字等非字符串 → str() 归一化返回，不裸 AttributeError
    def fake_post(*a, **k):
        return _ok_resp(content=42)

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    assert ask_agent([], "小明", "你是小明。", _CONFIG) == "42"


def test_ask_agent_missing_config_raises_distill_error():
    # 缺 base_url / 缺 model / 全缺（空配置）都应抛 DistillError，而非 KeyError 裸异常
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", {"model": {"api_key": "k", "model": "m"}})
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", {"model": {"base_url": "http://x", "api_key": "k"}})
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", {})


def test_ask_agent_network_error_raises_distill_error(monkeypatch):
    # httpx.post 抛 ConnectError（httpx.HTTPError 子类）→ 转 DistillError
    def raise_connect(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", raise_connect)
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", _CONFIG)


def test_ask_agent_http_status_error_raises_distill_error(monkeypatch):
    # HTTP 500：raise_for_status 抛 HTTPStatusError → 转 DistillError
    def raise_status(*a, **k):
        raise httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=httpx.Request("POST", "http://x/chat/completions"),
            response=None,
        )

    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": raise_status})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", _CONFIG)


def test_ask_agent_parse_error_raises_distill_error(monkeypatch):
    # 响应 JSON 无法解析（JSONDecodeError，ValueError 子类）→ 转 DistillError
    import json as _json

    def bad_json(self):
        raise _json.JSONDecodeError("Expecting value", "{bad", 0)

    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None, "json": bad_json})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", _CONFIG)


def test_ask_agent_empty_choices_raises_distill_error(monkeypatch):
    # 响应 {"choices": []} → resp.json()["choices"][0] 抛 IndexError → 转 DistillError
    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": []}})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", _CONFIG)


def test_ask_agent_list_response_raises_distill_error(monkeypatch):
    # 响应为裸数组 [] → resp.json()["choices"] 抛 TypeError（list indices must be integers）→ 转 DistillError
    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: []})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        ask_agent([], "小明", "你是小明。", _CONFIG)
