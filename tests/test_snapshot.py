from pathlib import Path

from weflow_agent.core.models import PersonaDoc
from weflow_agent.buzz.snapshot import build_snapshot, validate_snapshot, write_snapshot_json, _safe_filename


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
    try:
        validate_snapshot(bad)
        assert False, "应抛 ValueError"
    except ValueError:
        pass


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
    try:
        validate_snapshot(bad)
        assert False, "应抛 ValueError"
    except ValueError:
        pass


def test_snapshot_rejects_invalid_slug():
    bad = build_snapshot(_doc())
    bad["memory"] = {"level": "everything", "entries": [{"slug": "random", "body": "x"}]}
    try:
        validate_snapshot(bad)
        assert False, "slug 必须是 core 或 mem/ 前缀，应抛 ValueError"
    except ValueError:
        pass


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
        try:
            validate_snapshot(snap)
            assert False, f"slug {slug!r} 应被拒绝"
        except ValueError:
            pass


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
    assert _safe_filename("../outside") == ".._outside"
    assert (tmp_path / "a_b.agent.json").exists()


def test_validate_rejects_path_separators_in_name():
    for value in ("a/b", "a\\b"):
        snap = build_snapshot(_doc())
        snap["definition"]["name"] = value
        try:
            validate_snapshot(snap)
            assert False, f"definition.name 含路径分隔符 {value!r} 应被拒绝"
        except ValueError:
            pass


def test_validate_rejects_path_separators_in_display_name():
    for value in ("a/b", "a\\b"):
        snap = build_snapshot(_doc())
        snap["profile"]["displayName"] = value
        try:
            validate_snapshot(snap)
            assert False, f"profile.displayName 含路径分隔符 {value!r} 应被拒绝"
        except ValueError:
            pass
