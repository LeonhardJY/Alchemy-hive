"""chat_completion（共享 LLM 客户端）行为测试：json_mode 兼容回退、错误分类、重试。"""
import httpx
import pytest

from alchemy_hive.core.llm import chat_completion, LLMError

_CFG = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}


def _ok_resp(content: str = "ok"):
    class R:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": content}}]}
    return R()


def test_json_mode_fallback_when_400(monkeypatch):
    """供应商拒绝 response_format（HTTP 400）→ 自动去掉 json_mode 重试一次并成功。"""
    calls: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if json.get("response_format"):
            raise httpx.HTTPStatusError(
                "400 Bad Request", request=httpx.Request("POST", url),
                response=type("R", (), {"status_code": 400})())
        return _ok_resp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    out = chat_completion(_CFG, [{"role": "user", "content": "hi"}], json_mode=True)
    assert out == "ok"
    assert len(calls) == 2
    assert calls[0].get("response_format") == {"type": "json_object"}
    assert "response_format" not in calls[1]


def test_4xx_auth_error_clear_message(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        raise httpx.HTTPStatusError(
            "401 Unauthorized", request=httpx.Request("POST", url),
            response=type("R", (), {"status_code": 401})())

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(LLMError, match="HTTP 401"):
        chat_completion(_CFG, [{"role": "user", "content": "hi"}], json_mode=True)


def test_missing_config_no_request(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", lambda *a, **k: captured.append(k) or _ok_resp())
    with pytest.raises(LLMError, match="未配置模型"):
        chat_completion({"model": {"api_key": "k"}}, [{"role": "user", "content": "hi"}])
    assert captured == [], "配置缺失不应发起任何网络请求"


def test_connect_error_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(LLMError):
        chat_completion(_CFG, [{"role": "user", "content": "hi"}], max_retries=1, backoff=0)
    assert calls["n"] == 2  # 首次 + 1 次重试


def test_content_null_returns_empty(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _ok_resp(content=None)

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    assert chat_completion(_CFG, [{"role": "user", "content": "hi"}]) == ""


def test_max_tokens_sent_when_set(monkeypatch):
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _ok_resp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    chat_completion(_CFG, [{"role": "user", "content": "hi"}], max_tokens=10000)
    assert captured.get("max_tokens") == 10000


def test_max_tokens_omitted_when_none(monkeypatch):
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _ok_resp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    chat_completion(_CFG, [{"role": "user", "content": "hi"}])
    assert "max_tokens" not in captured


def test_deepseek_thinking_disabled(monkeypatch):
    """DeepSeek V4 思考模式会把 token 预算吃光、content 为 null → 默认关思考模式。"""
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _ok_resp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    chat_completion(
        {"model": {"base_url": "https://api.deepseek.com/v1", "api_key": "k", "model": "deepseek-v4-flash"}},
        [{"role": "user", "content": "hi"}],
    )
    assert captured.get("thinking") == {"type": "disabled"}


def test_non_deepseek_no_thinking_field(monkeypatch):
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _ok_resp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    chat_completion(_CFG, [{"role": "user", "content": "hi"}])  # base_url=http://x，非 DeepSeek
    assert "thinking" not in captured
