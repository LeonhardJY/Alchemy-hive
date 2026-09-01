"""Tests for incremental distillation: merge, timestamp extraction, summary, full pipeline."""

import json
from pathlib import Path

import pytest

from alchemy_hive.core.models import Message, PersonaDoc
from alchemy_hive.core.distill import (
    _build_persona_summary,
    _extract_last_timestamp,
    _merge_analysis,
    distill_incremental,
    DistillError,
)


# ---------------------------------------------------------------------------
# Helper: build a PersonaDoc quickly
# ---------------------------------------------------------------------------

def _make_doc(**overrides) -> PersonaDoc:
    defaults = dict(name="小明", display_name="小明")
    defaults.update(overrides)
    return PersonaDoc(**defaults)


# ---------------------------------------------------------------------------
# 1. _merge_analysis – deduplicates memories by slug
# ---------------------------------------------------------------------------

def test_merge_analysis_deduplicates_memories():
    old_doc = _make_doc(memory=[
        {"slug": "mem/食堂", "body": "一起在食堂研究菜单"},
        {"slug": "mem/军训", "body": "军训偷懒"},
    ])
    new_analysis = {
        "memories": [
            {"slug": "mem/食堂", "body": "食堂改版后又去了一次"},  # duplicate slug
            {"slug": "mem/旅行", "body": "一起去了厦门"},           # new
        ]
    }
    merged = _merge_analysis(old_doc, new_analysis, "小明")

    slugs = [m["slug"] for m in merged["memories"]]
    # "mem/食堂" appears only once (new version should NOT replace old; deduplicated by slug)
    assert slugs.count("mem/食堂") == 1
    assert "mem/军训" in slugs
    assert "mem/旅行" in slugs


# ---------------------------------------------------------------------------
# 2. _merge_analysis – merges expression_rules without duplicates
# ---------------------------------------------------------------------------

def test_merge_analysis_appends_rules():
    old_doc = _make_doc(expression_rules=["一次只说一句话", "多用语气词"])
    new_analysis = {
        "expression_rules": ["多用语气词", "禁用书面语", "语气要软"],
    }
    merged = _merge_analysis(old_doc, new_analysis, "小明")

    rules = merged["expression_rules"]
    assert "一次只说一句话" in rules          # kept from old
    assert "多用语气词" in rules               # shared – only one copy
    assert "禁用书面语" in rules              # new
    assert "语气要软" in rules                # new
    assert rules.count("多用语气词") == 1     # no duplicate


# ---------------------------------------------------------------------------
# 3. _merge_analysis – merges signature_phrases as set union
# ---------------------------------------------------------------------------

def test_merge_analysis_merges_phrases():
    old_doc = _make_doc(signature_phrases=["蛤", "是了"])
    new_analysis = {
        "signature_phrases": ["是了", "卧槽", "哈哈"],
    }
    merged = _merge_analysis(old_doc, new_analysis, "小明")

    phrases = set(merged["signature_phrases"])
    assert phrases == {"蛤", "是了", "卧槽", "哈哈"}


# ---------------------------------------------------------------------------
# 4. _merge_analysis – caps memories at _MAX_MEMORIES (60)
# ---------------------------------------------------------------------------

def test_merge_analysis_caps_memories():
    old_memories = [{"slug": f"old/{i}", "body": f"old-{i}"} for i in range(55)]
    old_doc = _make_doc(memory=old_memories)
    new_memories = [{"slug": f"new/{i}", "body": f"new-{i}"} for i in range(10)]
    new_analysis = {"memories": new_memories}

    merged = _merge_analysis(old_doc, new_analysis, "小明")
    # 55 old + 10 new = 65, but cap is 60 → kept = last 60
    assert len(merged["memories"]) == 60
    # oldest 5 should be dropped (old/0 .. old/4)
    all_slugs = {m["slug"] for m in merged["memories"]}
    assert "old/0" not in all_slugs
    assert "old/5" in all_slugs  # still present


# ---------------------------------------------------------------------------
# 5. _merge_analysis – preserves old relationship when new has none
# ---------------------------------------------------------------------------

def test_merge_analysis_preserves_relationship():
    old_doc = _make_doc(
        relationship="青梅竹马",
        relationship_arc="小学认识到现在",
        relationship_essence="像家人一样",
    )
    # new analysis has no relationship fields
    new_analysis = {"memories": [], "expression_rules": []}
    merged = _merge_analysis(old_doc, new_analysis, "小明")

    assert merged["relationship"] == "青梅竹马"
    assert merged["relationship_arc"] == "小学认识到现在"
    assert merged["relationship_essence"] == "像家人一样"


# ---------------------------------------------------------------------------
# 6. _extract_last_timestamp – from parsed JSON file
# ---------------------------------------------------------------------------

def test_extract_last_timestamp_from_persona(tmp_path):
    """_extract_last_timestamp 优先使用 PersonaDoc.last_distill_ts 字段。"""
    doc = _make_doc(memory=[], last_distill_ts="2025-12-01 14:00:00")
    ts = _extract_last_timestamp(doc)
    assert ts == "2025-12-01 14:00:00"


def test_extract_last_timestamp_from_parsed_fallback(tmp_path):
    """没有 last_distill_ts 时回退到记忆文本正则。"""
    doc = _make_doc(memory=[
        {"slug": "c", "body": "2024-06-15 一起吃饭"},
        {"slug": "d", "body": "2025-01-20 一起去旅行"},
    ])
    ts = _extract_last_timestamp(doc)
    assert ts == "2025-01-20"


# ---------------------------------------------------------------------------
# 7. _extract_last_timestamp – fallback to memory body regex
# ---------------------------------------------------------------------------

def test_extract_last_timestamp_fallback_to_memory():
    doc = _make_doc(memory=[
        {"slug": "a", "body": "2023-05-10 一起去爬山"},
        {"slug": "b", "body": "后面也联系过"},
    ])
    # No workdir -> no parsed file -> fallback to regex
    ts = _extract_last_timestamp(doc, workdir="", name="小明")
    # Regex captures \d{4}-\d{2}-\d{2} from memory body
    assert ts == "2023-05-10"


# ---------------------------------------------------------------------------
# 6b. _extract_last_timestamp – parsed file missing falls back to memory
# ---------------------------------------------------------------------------

def test_extract_last_timestamp_parsed_missing_falls_back(tmp_path):
    workdir = tmp_path / "project"
    workdir.mkdir(parents=True)
    # No parsed/ dir → fallback
    doc = _make_doc(memory=[
        {"slug": "m1", "body": "2024-08-20 发生了有趣的事"},
    ])
    ts = _extract_last_timestamp(doc, workdir=str(workdir), name="小明")
    assert ts == "2024-08-20"


# ---------------------------------------------------------------------------
# 7b. _extract_last_timestamp – no date anywhere returns None
# ---------------------------------------------------------------------------

def test_extract_last_timestamp_no_dates_returns_none():
    doc = _make_doc(memory=[{"slug": "a", "body": "一起去爬山很开心"}])
    ts = _extract_last_timestamp(doc, workdir="", name="小明")
    assert ts is None


# ---------------------------------------------------------------------------
# 8. _build_persona_summary – formatted output from PersonaDoc fields
# ---------------------------------------------------------------------------

def test_build_persona_summary():
    doc = _make_doc(
        relationship="好朋友",
        expression_rules=["一次只说一句话", "多用语气词"],
        signature_phrases=["蛤", "是了"],
        memory=[
            {"slug": "a", "body": "一起去食堂"},
            {"slug": "b", "body": "一起翘课"},
        ],
    )
    summary = _build_persona_summary(doc)

    assert "好朋友" in summary
    assert "一次只说一句话" in summary
    assert "蛤" in summary
    assert "一起去食堂" in summary
    assert "一起翘课" in summary


def test_build_persona_summary_empty_doc():
    doc = _make_doc()
    summary = _build_persona_summary(doc)
    assert summary == "（无）"


# ---------------------------------------------------------------------------
# 9. distill_incremental – full pipeline with mock LLM
# ---------------------------------------------------------------------------

def test_distill_incremental_merges_and_builds(tmp_path, monkeypatch):
    """End-to-end incremental distillation: old doc + new messages → merged persona."""
    import alchemy_hive.core.llm as llm_mod

    old_doc = _make_doc(
        relationship="好朋友",
        expression_rules=["一次只说一句话"],
        signature_phrases=["蛤"],
        memory=[{"slug": "mem/食堂", "body": "一起在食堂研究菜单"}],
        system_prompt="# 小明 Persona\n\n好朋友。",
    )

    new_analysis = {
        "display_name": "小明",
        "relationship": "好朋友",
        "expression_rules": ["一次只说一句话", "多用语气词"],
        "signature_phrases": ["蛤", "是了"],
        "memories": [
            {"slug": "mem/食堂", "body": "食堂改版了"},  # duplicate
            {"slug": "mem/旅行", "body": "一起去了厦门"},  # new
        ],
    }
    build_md = "# 小明 Persona v2\n\n好朋友 + 旅行记忆。"

    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        body = k.get("json") or {}
        if body.get("response_format"):
            content = json.dumps(new_analysis, ensure_ascii=False)
        else:
            content = build_md

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    monkeypatch.setattr("alchemy_hive.gui.actions.load_config", lambda path=None: {})

    msgs = [
        Message(sender="小明", content="最近去了厦门", timestamp="2025-10-01 10:00:00"),
        Message(sender="我", content="好玩吗", timestamp="2025-10-01 10:05:00"),
    ]
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    result = distill_incremental(msgs, "小明", config, old_doc, workdir=str(tmp_path))

    # Merged memories: old unique + new unique, deduped
    slugs = [m["slug"] for m in result.memory]
    assert "mem/食堂" in slugs
    assert "mem/旅行" in slugs
    assert slugs.count("mem/食堂") == 1

    # Merged rules
    assert "一次只说一句话" in result.expression_rules
    assert "多用语气词" in result.expression_rules

    # Merged phrases
    assert set(result.signature_phrases) >= {"蛤", "是了"}

    # system_prompt replaced by build output
    assert result.system_prompt == build_md

    # relationship preserved
    assert result.relationship == "好朋友"


# ---------------------------------------------------------------------------
# 10. distill_incremental – no new messages returns existing doc
# ---------------------------------------------------------------------------

def test_distill_incremental_no_new_messages_returns_existing(tmp_path):
    old_doc = _make_doc(
        memory=[{"slug": "m1", "body": "2025-01-01 旧记忆"}],
        system_prompt="old prompt",
    )
    msgs = [
        Message(sender="小明", content="hello", timestamp="2024-12-31 23:00:00"),  # before old timestamp
    ]
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    result = distill_incremental(msgs, "小明", config, old_doc, workdir=str(tmp_path))
    assert result is old_doc  # exact same object returned


# ---------------------------------------------------------------------------
# 11. distill_incremental – raises on empty messages / missing api_key
# ---------------------------------------------------------------------------

def test_distill_incremental_empty_messages_raises():
    old_doc = _make_doc()
    with pytest.raises(DistillError, match="没有新消息"):
        distill_incremental([], "小明", {}, old_doc)


def test_distill_incremental_no_api_key_raises():
    old_doc = _make_doc()
    msgs = [Message(sender="x", content="hi", timestamp="2099-01-01")]
    with pytest.raises(DistillError, match="未配置模型 API key"):
        distill_incremental(msgs, "小明", {}, old_doc)
