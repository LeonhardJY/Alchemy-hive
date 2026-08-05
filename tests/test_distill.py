import httpx
import pytest

from alchemy_hive.core.parser import parse_messages
from alchemy_hive.core.distill import distill, DistillError


def test_distill_no_api_key_raises(examples_dir):
    """无 api_key 时必须抛 DistillError，绝不走规则兜底。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    with pytest.raises(DistillError):  # 空配置 → 无 api_key
        distill(msgs, "小明", {})


def test_distill_missing_base_url_raises(examples_dir):
    """缺 base_url：API key 校验通过后 base_url 为 None，_llm_distill 兜底失败 → DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    with pytest.raises(DistillError):
        distill(msgs, "小明", {"model": {"api_key": "k", "model": "m"}})


def test_distill_missing_model_name_raises(examples_dir, monkeypatch):
    """缺 model 名：客户端提前校验，不发起任何请求（无需联网）→ 直接 DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k"}})
    assert captured == {}, "缺 model 时不应携带错误 model 名发起网络请求"


def test_distill_llm_failure_raises(examples_dir, monkeypatch):
    """LLM 调用失败（网络错误）时必须抛 DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    def fake_post(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        distill(msgs, "小明", config)


def test_distill_http_status_error_raises(examples_dir, monkeypatch):
    """HTTP 500：raise_for_status 抛 HTTPStatusError（httpx.HTTPError 子类）→ DistillError。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    class BadResponse:
        status_code = 500

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=httpx.Request("POST", "http://x/chat/completions"),
                response=None,
            )

        def json(self):
            return {}

    def fake_post(*a, **k):
        return BadResponse()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError):
        distill(msgs, "小明", config)


def test_distill_llm_success_path(examples_dir, monkeypatch):
    """LLM 成功路径：mock httpx 返回伪造 OpenAI 响应，断言 LLM 结构化字段被使用，
    并锁死"样本发往所配端点"（url/auth/model 与配置一致）。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    fake_llm_json = {
        "display_name": "書源",
        "relationship": "好朋友",
        "expression_rules": [
            "一次只说一句话",
            "多用语气词（蛤/嗷/emmm）",
            "禁用书面语和完整长句",
        ],
        "signature_phrases": ["蛤", "是了", "卧槽"],
        "example_replies": {
            "约饭": ["走，吃食堂", "6"],
            "惊讶": ["卧槽", "蛤？"],
        },
        "memory": [{"slug": "mem/1", "body": "一起在食堂研究菜单"}],
    }
    import json
    fake_resp_body = {
        "choices": [{"message": {"content": json.dumps(fake_llm_json, ensure_ascii=False)}}]
    }

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_resp_body

    captured: dict = {}

    def _fake_post(*args, **kwargs):
        captured.update(kwargs)
        captured["url"] = args[0]
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)

    config = {
        "model": {
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-fake",
            "model": "gpt-4",
        }
    }
    doc = distill(msgs, "小明", config)

    # 请求锁死：url 指向 base_url 的 /chat/completions，带 api_key，model 与配置一致
    url = captured["url"]
    assert url.startswith(config["model"]["base_url"]), url
    assert "/chat/completions" in url, url
    assert config["model"]["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == config["model"]["model"]

    # LLM 字段被保留
    assert doc.display_name == "書源"          # 用了模型的 display_name
    assert doc.relationship == "好朋友"
    assert len(doc.expression_rules) == 3
    assert "蛤" in doc.signature_phrases
    assert "约饭" in doc.example_replies
    assert len(doc.memory) == 1
    # C2: system_prompt 由结构化字段渲染，不为空
    assert doc.system_prompt
    assert "書源" in doc.system_prompt
    assert "# 表达硬规则" in doc.system_prompt
    assert "# 场景例句" in doc.system_prompt
    assert "约饭" in doc.system_prompt


def test_distill_renders_dot_skill_layers(examples_dir, monkeypatch):
    """dot-skill 风格：关系上下文/节奏/情绪逻辑/记忆余像 应进入 system_prompt。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    fake = {
        "display_name": "小明",
        "relationship": "好朋友",
        "relationship_context": "高中同桌，毕业后还常联系。",
        "expression_rules": ["一次只说一句话"],
        "signature_phrases": ["蛤"],
        "rhythm": "短句碎片连发。",
        "example_replies": {"约饭": ["走"]},
        "layers": {
            "closeness": "话匣子打开",
            "withdrawal": "只回……",
            "conflict": "玩笑带过",
            "repair": "甩个视频",
            "boundaries": "讨厌说教",
        },
        "memory": [{"slug": "core", "body": "食堂一起研究菜单"}],
        "memory_signature": "念旧但不说。",
    }

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": _json.dumps(fake, ensure_ascii=False)}}]}

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", lambda *a, **k: FakeResp())
    doc = distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
    assert "高中同桌，毕业后还常联系。" in doc.system_prompt
    assert "# 说话节奏" in doc.system_prompt and "短句碎片连发。" in doc.system_prompt
    assert "# 情绪逻辑" in doc.system_prompt
    assert "亲近时：话匣子打开" in doc.system_prompt
    assert "边界：讨厌说教" in doc.system_prompt
    assert "# 记忆余像" in doc.system_prompt and "念旧但不说。" in doc.system_prompt
