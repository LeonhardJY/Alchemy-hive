from pathlib import Path

from weflow_agent.core.parser import parse_messages
from weflow_agent.core.models import Message

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_parse_weflow_json():
    msgs = parse_messages(str(EXAMPLES_DIR / "chat.json"))
    assert len(msgs) == 2
    assert all(isinstance(m, Message) for m in msgs)
    assert all(not m.content.startswith("[") for m in msgs)
    assert any(m.content == "epic又要送了？" for m in msgs)


def test_parse_wechat_txt():
    msgs = parse_messages(str(EXAMPLES_DIR / "chat.txt"))
    assert len(msgs) >= 2
    assert msgs[0].sender == "张書源"


def test_parse_detects_direction():
    msgs = parse_messages(str(EXAMPLES_DIR / "chat.json"))
    assert any(m.sender == "我" for m in msgs)
