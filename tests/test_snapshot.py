from weflow_agent.core.models import PersonaDoc
from weflow_agent.buzz.snapshot import build_snapshot, validate_snapshot


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
