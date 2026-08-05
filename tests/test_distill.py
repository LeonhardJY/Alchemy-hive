import httpx
import pytest

from weflow_agent.core.parser import parse_messages
from weflow_agent.core.distill import distill, DistillError


def test_distill_no_api_key_raises(examples_dir):
    """无 api_key 时必须抛 DistillError，绝不走规则兜底。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    with pytest.raises(DistillError):  # 空配置 → 无 api_key
        distill(msgs, "张書源", {})


def test_distill_missing_base_url_raises(examples_dir):
    """缺 base_url：API key 校验通过后 base_url 为 None，_llm_distill 兜底失败 → DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    with pytest.raises(DistillError):
        distill(msgs, "张書源", {"model": {"api_key": "k", "model": "m"}})


def test_distill_missing_model_name_raises(examples_dir, monkeypatch):
    """缺 model 名：请求 json 的 model 为 None（不送真端点）→ 抛 DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)
    with pytest.raises(DistillError):
        distill(msgs, "张書源", {"model": {"base_url": "http://x", "api_key": "k"}})
    # 缺 model 时请求绝不应携带非空 model 名
    assert captured["json"]["model"] is None


def test_distill_llm_failure_raises(examples_dir, monkeypatch):
    """LLM 调用失败（网络错误）时必须抛 DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    def fake_post(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)
    with pytest.raises(DistillError):
        distill(msgs, "张書源", config)


def test_distill_http_status_error_raises(examples_dir, monkeypatch):
    """HTTP 500：raise_for_status 抛 HTTPStatusError（httpx.HTTPError 子类）→ DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    class BadResponse:
        status_code = 500

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=httpx.Request("POST", "http://x/chat/completions"),
                response=None,
            )

        def json(self):
            return {}

    def fake_post(*a, **k):
        return BadResponse()

    monkeypatch.setattr("weflow_agent.core.distill.httpx.post", fake_post)
    with pytest.raises(DistillError):
        distill(msgs, "张書源", config)


def test_distill_llm_success_path(examples_dir, monkeypatch):
    """LLM 成功路径：mock httpx 返回伪造 OpenAI 响应，断言 LLM 结构化字段被使用，
    并锁死"样本发往所配端点"（url/auth/model 与配置一致）。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    fake_llm_json = {
        "display_name": "書源",
        "relationship": "好朋友",
        "expression_rules": [
            "一次只说一句话",
            "多用语气词（蛤/嗷/emmm）",
            "禁用书面语和完整长句",
        ],
        "signature_phrases": ["蛤", "是了", "卧槽"],
        "example_replies": {
            "约饭": ["走，吃食堂", "6"],
            "惊讶": ["卧槽", "蛤？"],
        },
        "memory": [{"slug": "mem/1", "body": "一起在食堂研究菜单"}],
    }
    import json
    fake_resp_body = {
        "choices": [{"message": {"content": json.dumps(fake_llm_json, ensure_ascii=False)}}]
    }

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_resp_body

    captured: dict = {}

    def _fake_post(*args, **kwargs):
        captured.update(kwargs)
        captured["url"] = args[0]
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)

    config = {
        "model": {
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-fake",
            "model": "gpt-4",
        }
    }
    doc = distill(msgs, "张書源", config)

    # 请求锁死：url 指向 base_url 的 /chat/completions，带 api_key，model 与配置一致
    url = captured["url"]
    assert url.startswith(config["model"]["base_url"]), url
    assert "/chat/completions" in url, url
    assert config["model"]["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == config["model"]["model"]

    # LLM 字段被保留
    assert doc.display_name == "書源"          # 用了模型的 display_name
    assert doc.relationship == "好朋友"
    assert len(doc.expression_rules) == 3
    assert "蛤" in doc.signature_phrases
    assert "约饭" in doc.example_replies
    assert len(doc.memory) == 1
    # C2: system_prompt 由结构化字段渲染，不为空
    assert doc.system_prompt
    assert "書源" in doc.system_prompt
    assert "# 表达硬规则" in doc.system_prompt
    assert "# 场景例句" in doc.system_prompt
    assert "约饭" in doc.system_prompt
