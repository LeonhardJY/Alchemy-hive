"""Plugin registry + exporter 适配器测试。"""
import json

import pytest

from alchemy_hive.core.plugins import (
    register_source, register_exporter, get_source, get_exporter,
    list_sources, list_exporters, export_all,
)
from alchemy_hive.core.models import PersonaDoc


def _make_doc(name="小明", system_prompt="你是小明。"):
    return PersonaDoc(name=name, display_name=name, system_prompt=system_prompt)


# ---- Source adapter registry ----

class FakeSource:
    name = "fake"
    extensions = [".fake"]
    def detect(self, path):
        return True
    def parse(self, path, **kwargs):
        return []


def test_register_and_get_source():
    register_source(FakeSource())
    assert get_source("fake") is not None
    assert get_source("nonexistent") is None
    assert "fake" in list_sources()


# ---- Exporter adapter registry ----

class FakeExporter:
    name = "fake_exp"
    extension = ".fake"
    label = "Fake Export"
    def export(self, doc, out_dir, **kwargs):
        from pathlib import Path
        p = Path(out_dir) / f"{doc.name}.fake"
        p.write_text("fake", encoding="utf-8")
        return str(p)


def test_register_and_get_exporter():
    register_exporter(FakeExporter())
    assert get_exporter("fake_exp") is not None
    assert "fake_exp" in list_exporters()


def test_export_all_with_fake(tmp_path):
    register_exporter(FakeExporter())
    doc = _make_doc()
    paths = export_all(doc, str(tmp_path), formats=["fake_exp"])
    assert len(paths) == 1
    assert paths[0].endswith(".fake")


def test_export_all_filters_by_format(tmp_path):
    """只导出指定格式，不导出其他。"""
    register_exporter(FakeExporter())
    doc = _make_doc()
    paths = export_all(doc, str(tmp_path), formats=["nonexistent"])
    assert paths == []


# ---- Text exporter ----

def test_text_exporter(tmp_path):
    from alchemy_hive.exporters.text import TextExporter
    doc = _make_doc(system_prompt="你是小明，一个活泼的人。")
    p = TextExporter().export(doc, str(tmp_path))
    assert p.endswith(".txt")
    content = open(p, encoding="utf-8").read()
    assert "小明" in content
    assert "活泼" in content


def test_text_exporter_empty_prompt(tmp_path):
    from alchemy_hive.exporters.text import TextExporter
    doc = _make_doc(system_prompt="")
    p = TextExporter().export(doc, str(tmp_path))
    assert open(p, encoding="utf-8").read() == ""


# ---- Buzz exporter ----

def test_buzz_exporter(tmp_path):
    from alchemy_hive.exporters.buzz_exporter import BuzzExporter
    doc = _make_doc()
    p = BuzzExporter().export(doc, str(tmp_path))
    assert p.endswith(".agent.json")
    snap = json.loads(open(p, encoding="utf-8").read())
    assert snap["format"] == "buzz-agent-snapshot"
    assert snap["definition"]["name"] == "小明"

# ---- SillyTavern exporter ----

def test_sillytavern_exporter(tmp_path):
    from alchemy_hive.exporters.sillytavern import SillyTavernExporter
    doc = _make_doc(system_prompt="你是小明，一个活泼的朋友。")
    doc.memory = [{"slug": "core", "body": "一起吃饭", "trigger": "约饭", "significance": "友谊的起点"}]
    doc.signature_phrases = ["蛤", "是了"]
    doc.expression_rules = ["一次只说一句话"]
    p = SillyTavernExporter().export(doc, str(tmp_path))
    assert p.endswith(".sillytavern.json")
    card = json.loads(open(p, encoding="utf-8").read())
    assert card["spec"] == "chara_card_v2"
    assert card["spec_version"] == "2.0"
    assert card["data"]["name"] == "小明"
    assert card["data"]["system_prompt"] == "你是小明，一个活泼的朋友。"
    assert len(card["data"]["character_book"]["entries"]) == 1
    assert card["data"]["character_book"]["entries"][0]["keys"] == ["约饭"]
