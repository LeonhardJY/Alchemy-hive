from pathlib import Path

import pytest

from weflow_agent.core.models import PersonaDoc
from weflow_agent.core.safe import safe_filename
from weflow_agent.buzz.snapshot import build_snapshot, validate_snapshot, write_snapshot_json


def _doc() -> PersonaDoc:
    return PersonaDoc(
        name="张書源",
        display_name="张書源",
        system_prompt="你是张書源。\n一次只说一句话。",
    )


def test_snapshot_matches_v1_schema():
    snap = build_snapshot(_doc())
    assert snap["format"] == "buzz-agent-snapshot"
    assert snap["version"] == 1
    assert snap["definition"]["name"] == "张書源"
    assert snap["profile"]["displayName"] == "张書源"
    assert "张書源" in snap["definition"]["systemPrompt"]
    assert snap["memory"]["level"] == "none"
    validate_snapshot(snap)


def test_snapshot_rejects_empty_name():
    bad = build_snapshot(_doc())
    bad["definition"]["name"] = "  "
    with pytest.raises(ValueError):
        validate_snapshot(bad)


def test_snapshot_with_memory_uses_everything():
    doc = _doc()
    doc.memory = [{"slug": "core", "body": "2022 疫情网课一起用 AI 写小说"}]
    snap = build_snapshot(doc)
    assert snap["memory"]["level"] == "everything"
    assert snap["memory"]["entries"][0]["slug"] == "core"
    validate_snapshot(snap)


def test_snapshot_no_memory_stays_none():
    snap = build_snapshot(_doc())  # memory 为空
    assert snap["memory"]["level"] == "none"
    assert snap["memory"]["entries"] == []


def test_snapshot_rejects_level_none_with_entries():
    bad = build_snapshot(_doc())
    bad["memory"] = {"level": "none", "entries": [{"slug": "core", "body": "x"}]}
    with pytest.raises(ValueError):
        validate_snapshot(bad)


def test_snapshot_rejects_invalid_slug():
    bad = build_snapshot(_doc())
    bad["memory"] = {"level": "everything", "entries": [{"slug": "random", "body": "x"}]}
    with pytest.raises(ValueError):  # slug 必须是 core 或 mem/ 前缀
        validate_snapshot(bad)


def test_snapshot_slug_exact_match_accepts_core_and_mem():
    # core 恰好、mem/ 后跟非空后缀（含中文）均应通过
    for slug in ("core", "mem/寺庙还愿", "mem/a"):
        snap = build_snapshot(_doc())
        snap["memory"] = {"level": "everything", "entries": [{"slug": slug, "body": "x"}]}
        validate_snapshot(snap)  # 不应抛


def test_snapshot_rejects_slug_prefix_abuse():
    # corefoo（前缀粘连）、mem/ 单独、core/xxx 均拒绝
    for slug in ("corefoo", "mem/", "core/xxx"):
        snap = build_snapshot(_doc())
        snap["memory"] = {"level": "everything", "entries": [{"slug": slug, "body": "x"}]}
        with pytest.raises(ValueError):
            validate_snapshot(snap)


def test_write_snapshot_filename_uses_user_name(tmp_path):
    # display_name 与 name 不同：文件名必须以用户输入的 name 为准
    doc = PersonaDoc(name="张書源", display_name="模型的别称", system_prompt="你是张書源。")
    path = write_snapshot_json(doc, str(tmp_path))
    written = Path(path)
    assert written.name == "张書源.agent.json", f"文件名应为用户 name，实际 {written.name}"
    assert "模型的别称.agent.json" not in [p.name for p in tmp_path.iterdir()]
    snap = validate_snapshot(build_snapshot(doc))
    assert snap is None  # 校验通过


def test_write_snapshot_filename_sanitizes_illegal_chars(tmp_path):
    # 含非法字符的 name：安全清洗，绝不产生子目录/越界路径
    doc = PersonaDoc(name="a/b", display_name="张書源", system_prompt="你是张書源。")
    path = write_snapshot_json(doc, str(tmp_path))
    written = Path(path)
    assert written.parent == tmp_path, f"不应产生子目录，实际 {written.parent}"
    assert written.name == "a_b.agent.json", f"非法字符应替换为下划线，实际 {written.name}"
    assert safe_filename("../outside") == ".._outside"
    assert (tmp_path / "a_b.agent.json").exists()


def test_validate_rejects_path_separators_in_name():
    for value in ("a/b", "a\\b"):
        snap = build_snapshot(_doc())
        snap["definition"]["name"] = value
        with pytest.raises(ValueError):
            validate_snapshot(snap)


def test_validate_rejects_path_separators_in_display_name():
    for value in ("a/b", "a\\b"):
        snap = build_snapshot(_doc())
        snap["profile"]["displayName"] = value
        with pytest.raises(ValueError):
            validate_snapshot(snap)


# --- malformed 输入：统一抛明确 ValueError，而非 KeyError/AttributeError/TypeError ---


def test_snapshot_rejects_non_dict_root():
    with pytest.raises(ValueError, match="快照必须是对象"):
        validate_snapshot(["not", "a", "dict"])


def test_snapshot_rejects_missing_definition():
    snap = build_snapshot(_doc())
    del snap["definition"]
    with pytest.raises(ValueError, match="definition"):
        validate_snapshot(snap)


def test_snapshot_rejects_non_dict_definition():
    snap = build_snapshot(_doc())
    snap["definition"] = "张書源"
    with pytest.raises(ValueError, match="definition 必须是对象"):
        validate_snapshot(snap)


def test_snapshot_rejects_missing_profile():
    snap = build_snapshot(_doc())
    del snap["profile"]
    with pytest.raises(ValueError, match="profile"):
        validate_snapshot(snap)


def test_snapshot_rejects_non_dict_profile():
    snap = build_snapshot(_doc())
    snap["profile"] = ["张書源"]
    with pytest.raises(ValueError, match="profile 必须是对象"):
        validate_snapshot(snap)


def test_snapshot_rejects_non_str_name():
    snap = build_snapshot(_doc())
    snap["definition"]["name"] = None
    with pytest.raises(ValueError, match="definition.name 不能为空"):
        validate_snapshot(snap)


def test_snapshot_missing_memory_defaults_none():
    snap = build_snapshot(_doc())
    del snap["memory"]
    validate_snapshot(snap)  # 不应抛：memory 缺失默认 none
    snap["memory"] = None
    validate_snapshot(snap)  # 显式 null 同样默认 none


def test_snapshot_rejects_non_dict_memory():
    snap = build_snapshot(_doc())
    snap["memory"] = ["none"]
    with pytest.raises(ValueError, match="memory 必须是对象"):
        validate_snapshot(snap)


def test_snapshot_rejects_non_list_entries():
    snap = build_snapshot(_doc())
    snap["memory"] = {"level": "everything", "entries": {"core": {"body": "x"}}}
    with pytest.raises(ValueError, match="memory.entries 必须是数组"):
        validate_snapshot(snap)


def test_snapshot_rejects_non_dict_entry():
    snap = build_snapshot(_doc())
    snap["memory"] = {"level": "everything", "entries": ["core"]}
    with pytest.raises(ValueError, match="memory.entries\\[0\\] 必须是对象"):
        validate_snapshot(snap)


def test_snapshot_rejects_missing_slug():
    snap = build_snapshot(_doc())
    snap["memory"] = {"level": "everything", "entries": [{"body": "x"}]}
    with pytest.raises(ValueError, match="slug"):
        validate_snapshot(snap)


def test_snapshot_rejects_missing_body():
    snap = build_snapshot(_doc())
    snap["memory"] = {"level": "everything", "entries": [{"slug": "core"}]}
    with pytest.raises(ValueError, match="body"):
        validate_snapshot(snap)


def test_snapshot_rejects_non_str_body():
    # body 为数字/数组/dict/null：不静默 str() 强制通过，统一 ValueError
    for body in (123, ["x"], {"x": 1}, None):
        snap = build_snapshot(_doc())
        snap["memory"] = {"level": "everything", "entries": [{"slug": "core", "body": body}]}
        with pytest.raises(ValueError, match="body"):
            validate_snapshot(snap)


def test_snapshot_rejects_non_string_slug():
    # slug 为 None/数字：不应 TypeError，统一 ValueError
    for slug in (None, 123):
        snap = build_snapshot(_doc())
        snap["memory"] = {"level": "everything", "entries": [{"slug": slug, "body": "x"}]}
        with pytest.raises(ValueError, match="slug"):
            validate_snapshot(snap)
