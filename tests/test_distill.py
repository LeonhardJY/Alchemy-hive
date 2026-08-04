from weflow_agent.core.parser import parse_messages
from weflow_agent.core.distill import distill, _rule_fallback


def test_rule_fallback_produces_prompt():
    msgs = parse_messages("examples/chat.txt")
    doc = _rule_fallback(msgs, "张書源")
    assert doc.display_name == "张書源"
    assert "张書源" in doc.system_prompt
    assert "一次只说一句话" in doc.system_prompt  # 硬规则兜底必含


def test_distill_no_api_key_uses_fallback():
    msgs = parse_messages("examples/chat.txt")
    doc = distill(msgs, "张書源", {})  # 空配置 → 无 api_key → 规则兜底
    assert doc.system_prompt
