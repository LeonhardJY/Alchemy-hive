"""多平台导出格式的针对性测试：Telegram / WhatsApp / Instagram·Facebook 的结构与边界。

用 tmp_path 内联构造各平台的真实导出变体，覆盖：
识别、时间戳归一化、媒体/系统消息跳过、方向(--self)、错误回退。
"""
import json
import re

import pytest

from alchemy_hive.core.parser import parse_messages, detect_source


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---------- Telegram ----------

def _tg(messages):
    return json.dumps({"name": "chat", "type": "personal_chat", "id": 1, "messages": messages}, ensure_ascii=False)


def _tg_msg(**kw):
    base = {"id": 1, "type": "message", "date": "2023-07-24T09:29:09", "from": "小明", "text": "你好"}
    base.update(kw)
    return base


def test_telegram_entity_array_concat(tmp_path):
    path = _write(tmp_path, "tg.json", _tg([_tg_msg(text=["好，", {"type": "bold", "text": "楼下"}, "见"])]))
    assert parse_messages(path)[0].content == "好，楼下见"


def test_telegram_entity_array_link_without_text_ok(tmp_path):
    # 实体数组里的链接对象（有 url、text）应取 text，不产出垃圾
    path = _write(tmp_path, "tg.json", _tg([_tg_msg(text=["看 ", {"type": "link", "url": "https://x.com", "text": "这个"}])]))
    assert parse_messages(path)[0].content == "看 这个"


def test_telegram_service_and_media_skipped(tmp_path):
    path = _write(tmp_path, "tg.json", _tg([
        _tg_msg(id=1, text="在吗"),
        _tg_msg(id=2, type="service", text="小明 joined the group"),
        _tg_msg(id=3, text="", photo="photo.jpg"),
    ]))
    assert [m.content for m in parse_messages(path)] == ["在吗"]


def test_telegram_missing_from_becomes_unknown(tmp_path):
    assert parse_messages(_write(tmp_path, "tg.json", _tg([_tg_msg(**{"from": None})])))[0].sender == "unknown"


def test_telegram_iso_variants_normalized(tmp_path):
    cases = [
        ("2023-07-24T09:29:09", "2023-07-24 09:29:09"),
        ("2023-07-24T09:29:09+08:00", "2023-07-24 09:29:09"),
        ("2023-07-24T09:29:09Z", "2023-07-24 09:29:09"),
        ("2023-07-24 09:29:09", "2023-07-24 09:29:09"),
    ]
    for i, (date, expect) in enumerate(cases):
        path = _write(tmp_path, f"tg{i}.json", _tg([_tg_msg(date=date)]))
        assert parse_messages(path)[0].timestamp == expect


def test_telegram_self_default_and_custom(tmp_path):
    path = _write(tmp_path, "tg.json", _tg([
        _tg_msg(**{"from": "我"}), _tg_msg(**{"from": "小明"}, date="2023-07-24T09:29:10"),
    ]))
    assert [m.sender for m in parse_messages(path)] == ["我", "小明"]
    path2 = _write(tmp_path, "tg2.json", _tg([
        _tg_msg(**{"from": "Alice"}), _tg_msg(**{"from": "Bob"}, date="2023-07-24T09:29:10"),
    ]))
    assert [m.sender for m in parse_messages(path2, self_aliases=["Alice"])] == ["我", "Bob"]


def test_telegram_media_filename_text_skipped(tmp_path):
    path = _write(tmp_path, "tg.json", _tg([_tg_msg(text="photo.jpg")]))
    assert parse_messages(path) == []


# ---------- WhatsApp ----------

def test_whatsapp_standard_parse(tmp_path):
    text = (
        "[07/24/23, 9:29:09 AM] 小明: 晚上一起吃饭？\n"
        "[07/24/23, 9:31:53 AM] Alice: 好，老地方见\n"
        "[07/24/23, 9:32:10 AM] 小明: image.jpg\n"
        "[07/24/23, 9:32:15 AM] 小明: 我给你看个东西\n"
        "就是这个\n"
    )
    path = _write(tmp_path, "wa.txt", text)
    msgs = parse_messages(path, self_aliases=["Alice"])
    assert detect_source(path) == "whatsapp"
    assert len(msgs) == 3                     # image.jpg 媒体行跳过
    assert msgs[0].timestamp == "2023-07-24 09:29:09"
    assert msgs[1].sender == "我"              # --self Alice
    assert msgs[2].content == "我给你看个东西\n就是这个"  # 续行接上


def test_whatsapp_am_pm_and_missing_seconds(tmp_path):
    cases = [
        ("[07/24/23, 12:00:00 AM] A: 早", "2023-07-24 00:00:00"),
        ("[07/24/23, 12:00:00 PM] A: 午", "2023-07-24 12:00:00"),
        ("[07/24/23, 9:29 PM] A: 晚", "2023-07-24 21:29:00"),
        ("[07/24/23, 11:59:59 PM] A: 末", "2023-07-24 23:59:59"),
    ]
    for i, (line, expect) in enumerate(cases):
        path = _write(tmp_path, f"wa{i}.txt", line + "\n")
        assert parse_messages(path)[0].timestamp == expect


def test_whatsapp_system_lines_skipped(tmp_path):
    text = (
        "[07/24/23, 9:29:09 AM] 你创建了群组\n"      # 无"发送者:" → 系统行，跳过
        "[07/24/23, 9:29:11 AM] 小明: 在吗\n"
    )
    msgs = parse_messages(_write(tmp_path, "wa.txt", text))
    assert len(msgs) == 1
    assert msgs[0].content == "在吗"


def test_whatsapp_content_with_colon_preserved(tmp_path):
    path = _write(tmp_path, "wa.txt", "[07/24/23, 9:29:09 AM] 小明: 晚上好：明天见\n")
    assert parse_messages(path)[0].content == "晚上好：明天见"


def test_whatsapp_media_variants_skipped(tmp_path):
    names = ["image.jpg", "video.mp4", "audio.opus", "IMG_20230724.jpg", "photo.png", "doc.pdf"]
    text = "\n".join(f"[07/24/23, 9:29:{i:02d} AM] 小明: {n}" for i, n in enumerate(names)) + "\n"
    assert parse_messages(_write(tmp_path, "wa.txt", text)) == []


def test_whatsapp_two_digit_and_single_digit_date(tmp_path):
    assert parse_messages(_write(tmp_path, "wa1.txt", "[07/24/99, 9:29:09 AM] 小明: 在\n"))[0].timestamp == "1999-07-24 09:29:09"
    assert parse_messages(_write(tmp_path, "wa2.txt", "[9/5/23, 9:29:09 AM] 小明: 在\n"))[0].timestamp == "2023-09-05 09:29:09"


# ---------- Instagram / Facebook（Meta 共用格式） ----------

def _meta(messages):
    return json.dumps({"participants": [], "messages": messages}, ensure_ascii=False)


def _meta_msg(**kw):
    base = {"sender_name": "小明", "timestamp_ms": 1690252320000, "content": "在吗", "type": "Generic"}
    base.update(kw)
    return base


def test_meta_sorted_newest_first(tmp_path):
    path = _write(tmp_path, "ig.json", _meta([
        _meta_msg(content="好，老地方见", timestamp_ms=1690252335000),
        _meta_msg(content="晚上一起吃饭？", timestamp_ms=1690252330000),
        _meta_msg(sender_name="Alice", content="在吗", timestamp_ms=1690252320000),
    ]))
    msgs = parse_messages(path, self_aliases=["Alice"])
    assert detect_source(path) == "meta"
    assert [m.content for m in msgs] == ["在吗", "晚上一起吃饭？", "好，老地方见"]  # 新的在前 → 升序
    assert [m.sender for m in msgs] == ["我", "小明", "小明"]


def test_meta_share_and_media_skipped(tmp_path):
    path = _write(tmp_path, "ig.json", _meta([
        _meta_msg(id=1, content="在吗"),
        _meta_msg(id=2, type="Share", content=None),   # 无 content → 跳过
        _meta_msg(id=3, content="photo.jpg"),           # 媒体文件名 → 跳过
    ]))
    assert [m.content for m in parse_messages(path)] == ["在吗"]


def test_meta_missing_sender_becomes_unknown(tmp_path):
    path = _write(tmp_path, "ig.json", _meta([{"timestamp_ms": 1, "content": "在吗"}]))
    assert parse_messages(path)[0].sender == "unknown"


def test_meta_timestamp_variants(tmp_path):
    path_int = _write(tmp_path, "ig_int.json", _meta([_meta_msg(timestamp_ms=1690252320000)]))
    path_str = _write(tmp_path, "ig_str.json", _meta([_meta_msg(timestamp_ms="1690252320000")]))
    path_none = _write(tmp_path, "ig_none.json", _meta([_meta_msg(timestamp_ms=None)]))
    ts_int = parse_messages(path_int)[0].timestamp
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", ts_int)
    assert parse_messages(path_str)[0].timestamp == ts_int     # 字符串时间戳同样归一化
    assert parse_messages(path_none)[0].timestamp == ""


# ---------- 检测与通用兜底 ----------

def test_detect_generic_json(tmp_path):
    path = _write(tmp_path, "g.json", json.dumps([
        {"sender": "Alice", "content": "在吗", "timestamp": "2023-01-01 00:00:00"},
    ], ensure_ascii=False))
    assert detect_source(path) == "generic_json"
    assert parse_messages(path, self_aliases=["Alice"])[0].sender == "我"


def test_detect_generic_single_line_txt(tmp_path):
    path = _write(tmp_path, "g.txt", "Alice: 晚上好\nBob: 回见\n")
    assert detect_source(path) == "generic_txt"
    assert [m.sender for m in parse_messages(path, self_aliases=["Alice"])] == ["我", "Bob"]


def test_garbage_txt_raises_clear_error(tmp_path):
    path = _write(tmp_path, "garbage.txt", "这只是一段普通文字\n没有任何时间戳\n")
    assert detect_source(path) == "generic_txt"
    with pytest.raises(ValueError, match="时间戳"):
        parse_messages(path)


# ---------- 强制平台与错误回退 ----------

def test_forced_wrong_json_platform_falls_back(tmp_path):
    # 对 Meta 结构强选 Telegram（无 type=="message" → 解析 0 条）→ 回退自动识别出 1 条
    path = _write(tmp_path, "meta.json", _meta([_meta_msg()]))
    msgs = parse_messages(path, source="telegram")
    assert [m.content for m in msgs] == ["在吗"]


def test_forced_txt_platform_on_json_uses_auto(tmp_path):
    # 对 JSON 强选 WhatsApp（txt 平台）→ 扩展名不符，直接按自动识别
    path = _write(tmp_path, "chat.json", json.dumps([{"sender": "a", "content": "在吗"}]))
    assert parse_messages(path, source="whatsapp")[0].content == "在吗"
