import httpx
import pytest

from weflow_agent.core.parser import parse_messages
from weflow_agent.core.distill import distill, DistillError


def test_distill_no_api_key_raises():
    """无 api_key 时必须抛 DistillError，绝不走规则兜底。"""
    msgs = parse_messages("examples/chat.txt")
    try:
        distill(msgs, "张書源", {})  # 空配置 → 无 api_key
        assert False, "无 key 应抛 DistillError"
    except DistillError:
        pass


def test_distill_llm_failure_raises(monkeypatch):
    """LLM 调用失败（网络错误）时必须抛 DistillError。"""
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


def test_distill_llm_success_path(monkeypatch):
    """LLM 成功路径：mock httpx 返回伪造 OpenAI 响应，断言 LLM 结构化字段被使用。"""
    msgs = parse_messages("examples/chat.txt")
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

    def _fake_post(*args, **kwargs):
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
