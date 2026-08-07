from pathlib import Path
import json

import pytest

from alchemy_hive.core.parser import parse_messages
from alchemy_hive.core.models import Message

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
    assert msgs[0].sender == "小明"


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


def test_direction_falsy_but_self_alias_normalizes(tmp_path):
    """isSend=false 但 sender 是本人别名（忽略大小写/空白）→ 仍归一化为"我"，
    避免下游 extract_pairs 只认精确值把本人误判为对方。"""
    for flag in (0, False, "0", "false", "no"):
        f = tmp_path / f"falsy_{flag}.json"
        f.write_text(json.dumps([
            {"isSend": flag, "senderUsername": "  ME  ", "createTime": "2023-01-01 00:00:00", "msgContent": "hi"}
        ], ensure_ascii=False), encoding="utf-8")
        msgs = parse_messages(str(f))
        assert len(msgs) == 1
        assert msgs[0].sender == "我", f"isSend={flag!r} 但 sender='ME' 应归一化为本人"


def test_direction_falsy_non_alias_keeps_sender(tmp_path):
    """isSend=false 且 sender 非本人别名 → 保持原 sender，不被误归一化。"""
    f = tmp_path / "falsy_other.json"
    f.write_text(json.dumps([
        {"isSend": 0, "senderUsername": "小明", "createTime": "2023-01-01 00:00:00", "msgContent": "对方消息"}
    ], ensure_ascii=False), encoding="utf-8")
    msgs = parse_messages(str(f))
    assert len(msgs) == 1
    assert msgs[0].sender == "小明"


def test_direction_truthy_overrides_non_alias_sender(tmp_path):
    """isSend=true 且 sender 非本人别名（如平台账号）→ 仍判本人。"""
    for flag in (True, 1, "1"):
        f = tmp_path / f"truthy_{flag}.json"
        f.write_text(json.dumps([
            {"isSend": flag, "senderUsername": "abc", "createTime": "2023-01-01 00:00:00", "msgContent": "hi"}
        ], ensure_ascii=False), encoding="utf-8")
        msgs = parse_messages(str(f))
        assert len(msgs) == 1
        assert msgs[0].sender == "我", f"isSend={flag!r} 应判为本人消息"


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
        "2023-07-24 09:29:09 '小明'\n"
        "epic又要送了？\n"
        "2023-07-24 09:31:53 '我'\n"
        "我看看\n"
    )
    f.write_bytes(content.encode("gbk"))
    msgs = parse_messages(str(f))
    assert len(msgs) == 2
    assert msgs[0].sender == "小明"
    assert msgs[0].content == "epic又要送了？"
    assert msgs[1].sender == "我"
    assert msgs[1].content == "我看看"


def test_parse_file_not_found_raises(tmp_path):
    """文件不存在 → FileNotFoundError（CLI 统一错误边界捕获），而非空列表。"""
    with pytest.raises(FileNotFoundError, match="文件不存在"):
        parse_messages(str(tmp_path / "nope.txt"))


def test_parse_unknown_extension_raises(tmp_path):
    """未知扩展名（.md）→ ValueError，而非静默按 txt 解析。"""
    f = tmp_path / "chat.md"
    f.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="不支持的文件类型"):
        parse_messages(str(f))


def test_parse_top_level_scalar_raises(tmp_path):
    """顶层既非数组也非对象（如裸字符串/数字）→ ValueError。"""
    for i, raw in enumerate(('"just a string"', "123", "true")):
        f = tmp_path / f"scalar_{i}.json"
        f.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError, match="无法识别的 WeFlow JSON 结构"):
            parse_messages(str(f))


def test_parse_messages_not_list_raises(tmp_path):
    """顶层 dict 的 messages/data 键存在但值非数组 → ValueError。"""
    f = tmp_path / "msgs_not_list.json"
    f.write_text(json.dumps({"messages": "oops"}), encoding="utf-8")
    with pytest.raises(ValueError, match="无法识别的 WeFlow JSON 结构"):
        parse_messages(str(f))


def test_parse_skips_non_dict_records(tmp_path):
    """数组内含非 dict 元素（数字/字符串）→ 跳过而非抛错，保留可解析消息。"""
    f = tmp_path / "mixed.json"
    f.write_text(json.dumps([
        {"msgContent": "hi", "senderUsername": "me", "createTime": "2023-01-01 00:00:00"},
        "not-a-dict",
        42,
    ]), encoding="utf-8")
    msgs = parse_messages(str(f))
    assert len(msgs) == 1
    assert msgs[0].content == "hi"


# ---- 大 txt 与格式健壮性（本地测试，不发 API）----


def test_parse_large_txt(tmp_path):
    """大 txt（10 万行）流式解析：消息数、首尾正确，不整读文件。"""
    f = tmp_path / "big.txt"
    with f.open("w", encoding="utf-8") as fh:
        for i in range(100_000):
            fh.write(f"2023-07-24 09:29:09 '小明'\n消息{i}\n")
    msgs = parse_messages(str(f))
    assert len(msgs) == 100_000
    assert msgs[0].content == "消息0"
    assert msgs[-1].content == "消息99999"


def test_parse_txt_special_whitespace_separator(tmp_path):
    """微信导出用  (U+2005) 等特殊空白分隔时间戳与发送者 → 应正常解析。"""
    f = tmp_path / "ws.txt"
    f.write_text("2023-07-24 09:29:09 '小明'\n在吗？\n", encoding="utf-8")
    msgs = parse_messages(str(f))
    assert len(msgs) == 1
    assert msgs[0].sender == "小明"
    assert msgs[0].content == "在吗？"


def test_parse_txt_unquoted_sender(tmp_path):
    """发送者不带引号（'2023-07-24 09:29:09 小明'）→ 应正常解析。"""
    f = tmp_path / "unquoted.txt"
    f.write_text("2023-07-24 09:29:09 小明\n在吗？\n", encoding="utf-8")
    msgs = parse_messages(str(f))
    assert len(msgs) == 1
    assert msgs[0].sender == "小明"


def test_parse_txt_single_digit_hour(tmp_path):
    """小时为个位数（9:29:09 而非 09:29:09）→ 应正常解析。"""
    f = tmp_path / "hour.txt"
    f.write_text("2023-07-24 9:29:09 '小明'\n早\n", encoding="utf-8")
    msgs = parse_messages(str(f))
    assert len(msgs) == 1
    assert msgs[0].content == "早"


def test_parse_garbage_txt_raises(tmp_path):
    """整份 txt 没有时间戳行（不是微信导出）→ 明确报错，而非产出 unknown 发送者消息。"""
    f = tmp_path / "garbage.txt"
    f.write_text("这只是一段普通文字\n没有任何时间戳\n", encoding="utf-8")
    with pytest.raises(ValueError, match="时间戳"):
        parse_messages(str(f))


def test_parse_empty_txt_returns_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    assert parse_messages(str(f)) == []
