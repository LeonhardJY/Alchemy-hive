"""Chat session 测试（mock LLM）。"""
import pytest

from alchemy_hive.core.chat import ChatSession, create_session
from alchemy_hive.core.models import PersonaDoc
from alchemy_hive.core.llm import LLMError


def _make_session(monkeypatch, system_prompt="你是小明。"):
    def fake_post(*a, **k):
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": "你好！"}}]},
        })()
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    return ChatSession(system_prompt=system_prompt, config={"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}, name="小明")


def test_chat_session_send(monkeypatch):
    session = _make_session(monkeypatch)
    reply = session.send("你好")
    assert reply == "你好！"
    assert len(session.history) == 2  # user + assistant


def test_chat_session_history_grows(monkeypatch):
    session = _make_session(monkeypatch)
    session.send("第一条")
    session.send("第二条")
    assert len(session.history) == 4


def test_chat_session_reset(monkeypatch):
    session = _make_session(monkeypatch)
    session.send("消息")
    session.reset()
    assert len(session.history) == 0


def test_chat_session_send_failure_rolls_back(monkeypatch):
    def fake_post(*a, **k):
        raise LLMError("网络错误")
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    session = ChatSession(
        system_prompt="test",
        config={"model": {"base_url": "http://x", "api_key": "k", "model": "m"}},
        name="test",
    )
    with pytest.raises(LLMError):
        session.send("hello")
    assert len(session.history) == 0  # user message rolled back


def test_create_session_from_persona(tmp_path, monkeypatch):
    """create_session 从 persona JSON 文件加载 system_prompt。"""
    def fake_post(*a, **k):
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": "嗨！"}}]},
        })()
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)

    persona = PersonaDoc(name="小明", display_name="小明", system_prompt="你是小明。")
    p = tmp_path / "小明.json"
    p.write_text(persona.model_dump_json(), encoding="utf-8")

    session = create_session(str(p), {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
    assert session.name == "小明"
    reply = session.send("你好")
    assert reply == "嗨！"
