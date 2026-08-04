from pathlib import Path
import json

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


def test_direction_bool_and_float(tmp_path):
    """回归：布尔/浮点方向标志不应被 _probe 字符串化误判。"""
    # isSend=true (JSON boolean)
    bool_file = tmp_path / "bool.json"
    bool_file.write_text(json.dumps([
        {"isSend": True, "senderUsername": "me", "createTime": "2023-01-01 00:00:00", "msgContent": "bool test"}
    ], ensure_ascii=False), encoding="utf-8")
    msgs_bool = parse_messages(str(bool_file))
    assert len(msgs_bool) == 1
    assert msgs_bool[0].sender == "我"

    # isSend=1.0 (JSON number, not int)
    float_file = tmp_path / "float.json"
    float_file.write_text(json.dumps([
        {"isSend": 1.0, "senderUsername": "me", "createTime": "2023-01-01 00:00:01", "msgContent": "float test"}
    ], ensure_ascii=False), encoding="utf-8")
    msgs_float = parse_messages(str(float_file))
    assert len(msgs_float) == 1
    assert msgs_float[0].sender == "我"
