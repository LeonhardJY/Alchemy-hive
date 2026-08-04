from pathlib import Path
import json

import pytest

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


def test_direction_string_markers(tmp_path):
    """字符串方向标记 "1"/"true"/"send"/"yes" 应判为本人消息，而非走别名误判。"""
    for flag in ("1", "true", "send", "yes"):
        f = tmp_path / f"str_{flag}.json"
        f.write_text(json.dumps([
            {"isSend": flag, "senderUsername": "me", "createTime": "2023-01-01 00:00:00", "msgContent": "hi"}
        ], ensure_ascii=False), encoding="utf-8")
        msgs = parse_messages(str(f))
        assert len(msgs) == 1
        assert msgs[0].sender == "我", f"isSend={flag!r} 应判为本人消息"


def test_direction_string_falls_back_to_alias(tmp_path):
    """字符串方向标记无匹配时仍走别名推断（"self" 仍判本人）。"""
    f = tmp_path / "alias.json"
    f.write_text(json.dumps([
        {"isSend": "self", "senderUsername": "me", "createTime": "2023-01-01 00:00:00", "msgContent": "alias test"}
    ], ensure_ascii=False), encoding="utf-8")
    msgs = parse_messages(str(f))
    assert len(msgs) == 1
    assert msgs[0].sender == "我"


def test_invalid_json_structure_raises(tmp_path):
    """顶层 dict 既无 messages 也无 data 键 → 抛 ValueError，而非静默返回空列表。"""
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"foo": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="无法识别的 WeFlow JSON 结构"):
        parse_messages(str(f))


def test_valid_empty_json_structure_returns_empty(tmp_path):
    """messages/data 键存在但为空数组是合法空 → 返回空列表，不抛错。"""
    for key in ("messages", "data"):
        f = tmp_path / f"empty_{key}.json"
        f.write_text(json.dumps({key: []}), encoding="utf-8")
        assert parse_messages(str(f)) == []


def test_parse_gbk_txt(tmp_path):
    """GBK 编码的微信导出 txt（含中文与 '时间戳 发送者' 行）应能解析出消息。"""
    f = tmp_path / "gbk.txt"
    content = (
        "2023-07-24 09:29:09 '张書源'\n"
        "epic又要送了？\n"
        "2023-07-24 09:31:53 '我'\n"
        "我看看\n"
    )
    f.write_bytes(content.encode("gbk"))
    msgs = parse_messages(str(f))
    assert len(msgs) == 2
    assert msgs[0].sender == "张書源"
    assert msgs[0].content == "epic又要送了？"
    assert msgs[1].sender == "我"
    assert msgs[1].content == "我看看"
