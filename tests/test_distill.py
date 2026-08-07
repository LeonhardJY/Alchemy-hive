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
    """LLM 调用失败（网络错误）时必须抛 DistillError，且信息包含具体原因与阶段。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    def fake_post(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError, match="分析阶段") as exc:
        distill(msgs, "小明", config)
    assert "无法连接" in str(exc.value), "应暴露底层原因而非通用提示"


def test_distill_timeout_surfaces_cause(examples_dir, monkeypatch):
    """请求超时 → 错误信息包含"超时"，用户能据此判断（国内网络常见）。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    def fake_post(*a, **k):
        raise httpx.TimeoutException("timed out", request=httpx.Request("POST", "http://x/chat/completions"))

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError, match="超时"):
        distill(msgs, "小明", config)


def test_distill_parse_failure_exposes_raw_response(examples_dir, monkeypatch):
    """模型返回非 JSON（如空内容/普通文字）→ 错误信息暴露原始返回开头 + 请求端点，便于定位。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}
    prose = "你好，我是小明，我平时喜欢打游戏。"

    def fake_post(url, headers=None, json=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": prose}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError) as exc:
        distill(msgs, "小明", config)
    msg = str(exc.value)
    assert "不是 JSON" in msg or "空内容" in msg
    assert prose[:20] in msg, "应暴露模型原始返回片段"
    assert "http://x/chat/completions" in msg and "model=m" in msg, "应暴露请求端点与模型名"


def test_distill_empty_response_exposes_hint(examples_dir, monkeypatch):
    """模型返回 content 为空（如思考模式/content:null）→ 错误信息提示检查计费/余额/模型名。"""
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    config = {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}

    def fake_post(url, headers=None, json=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": None}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    with pytest.raises(DistillError, match="空内容"):
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


def test_distill_two_pass_pipeline(examples_dir, monkeypatch):
    """两阶段：analyze(JSON) → build(Markdown)。system_prompt=build 输出，记忆映射进 doc，
    build 请求确实携带分析 JSON（含 layers/记忆 quote），且请求锁死发往所配端点。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    analysis = {
        "display_name": "書源",
        "relationship": "好朋友",
        "relationship_context": "高中同桌，毕业后还常联系。",
        "expression_rules": ["一次只说一句话", "多用语气词（蛤/嗷）", "禁用书面语和完整长句"],
        "signature_phrases": ["蛤", "是了", "卧槽"],
        "rhythm": "短句碎片连发。",
        "example_replies": {"约饭": ["走，吃食堂", "6"], "惊讶": ["卧槽"]},
        "layers": {"closeness": "话匣子打开", "withdrawal": "只回……", "conflict": "玩笑带过",
                   "repair": "甩个视频", "boundaries": "讨厌说教", "care": "秒回"},
        "memories": [{"slug": "mem/食堂", "body": "一起在食堂研究菜单", "quote": "走，吃食堂", "trigger": "约饭"}],
        "memory_signature": "念旧但不说。",
    }
    build_md = ("# 書源 — Persona\n\n## Layer 0 核心性格\n- 一次只说一句话\n\n"
                "## Layer 5 记忆库\n### 记忆 1：食堂\n- 一句话：一起在食堂研究菜单")
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update({"url": url, "headers": headers, "body": json})
        payload = build_md if not (json or {}).get("response_format") else _json.dumps(analysis, ensure_ascii=False)
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": payload}}]}
        return FakeResp()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    config = {"model": {"base_url": "https://api.example.com/v1", "api_key": "sk-fake", "model": "gpt-4"}}
    doc = distill(msgs, "小明", config)

    # captured 是最后一次调用（build 请求）：锁死发往所配端点
    assert captured["url"].startswith(config["model"]["base_url"])
    assert "/chat/completions" in captured["url"]
    assert config["model"]["api_key"] in captured["headers"]["Authorization"]
    assert captured["body"]["model"] == config["model"]["model"]
    assert captured["body"].get("max_tokens") == 8000  # 长 persona 输出上限

    # build 请求真的带上了分析 JSON（记忆 quote + layers）
    build_content = captured["body"]["messages"][0]["content"]
    assert "memories" in build_content and "一起在食堂研究菜单" in build_content
    assert "closeness" in build_content

    # 分析字段保留 + 记忆映射进 doc
    assert doc.display_name == "書源"
    assert doc.relationship == "好朋友"
    assert len(doc.expression_rules) == 3
    assert "蛤" in doc.signature_phrases
    assert "约饭" in doc.example_replies
    assert len(doc.memory) == 1 and doc.memory[0]["slug"] == "mem/食堂"

    # system_prompt = build 输出
    assert doc.system_prompt == build_md


def test_distill_build_failure_falls_back_to_structured(examples_dir, monkeypatch):
    """build 阶段 LLM 失败 → 降级结构化渲染，仍返回非空 persona + 记忆，绝不空。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    analysis = {
        "display_name": "小明",
        "relationship": "好朋友",
        "expression_rules": ["一次只说一句话"],
        "signature_phrases": ["蛤"],
        "example_replies": {"约饭": ["走"]},
        "memories": [{"slug": "core", "body": "食堂一起研究菜单"}],
    }

    def fake_post(url, headers=None, json=None, timeout=None):
        if (json or {}).get("response_format"):
            class R:
                def raise_for_status(self): pass
                def json(self): return {"choices": [{"message": {"content": _json.dumps(analysis, ensure_ascii=False)}}]}
            return R()
        raise httpx.ConnectError("build stage offline")

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    doc = distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
    assert doc.system_prompt and "# 表达硬规则" in doc.system_prompt
    assert "蛤" in doc.system_prompt
    assert len(doc.memory) == 1 and doc.memory[0]["body"] == "食堂一起研究菜单"


def test_distill_max_tokens_rejected_falls_back(examples_dir, monkeypatch):
    """供应商拒绝 max_tokens（400）→ 自动去掉重试，蒸馏仍成功。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    analysis = {"display_name": "小明", "relationship": "好朋友",
                "expression_rules": ["一次只说一句话"],
                "memories": [{"slug": "core", "body": "食堂"}]}
    build_md = "你是小明。\n一次只说一句话。"
    calls: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        body = json or {}
        calls.append(body)
        if body.get("max_tokens"):
            raise httpx.HTTPStatusError(
                "400 Bad Request", request=httpx.Request("POST", url),
                response=type("R", (), {"status_code": 400})())
        content = _json.dumps(analysis, ensure_ascii=False) if body.get("response_format") else build_md
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": content}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    doc = distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
    assert doc.system_prompt == build_md
    assert any("max_tokens" not in c for c in calls), "带 max_tokens 被拒后应有去掉 max_tokens 的重试"


def test_sample_text_keeps_full_content():
    """样本不截断正文（对齐 dot-skill）：300 字消息应完整进入 analyze 样本。"""
    from alchemy_hive.core.distill import _sample_text
    from alchemy_hive.core.models import Message
    long_content = "这是一条很长的消息" + "字" * 300
    msgs = [Message(sender="小明", content=long_content, timestamp="2023-01-01 00:00:00")]
    assert long_content in _sample_text(msgs)


def test_distill_manual_profile_flows_to_analyze(examples_dir, monkeypatch):
    """手动画像（最高优先级）应进入 analyze prompt，且不出现"未提供"占位。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    analyze_contents: list[str] = []
    analysis = {"display_name": "小明", "relationship": "好朋友", "expression_rules": ["一次只说一句话"]}

    def fake_post(url, headers=None, json=None, timeout=None):
        body = json or {}
        if body.get("response_format"):
            analyze_contents.append(body["messages"][0]["content"])
            content = _json.dumps(analysis, ensure_ascii=False)
        else:
            content = "# 小明 — Persona"
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": content}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}},
            manual_profile="INTJ 摩羯座 爱吐槽")
    assert analyze_contents and "INTJ 摩羯座 爱吐槽" in analyze_contents[0]
    assert "（用户未提供" not in analyze_contents[0]


def test_distill_corrections_flow_to_build(examples_dir, monkeypatch):
    """用户纠正应进入 build 的 Correction 记录，并持久化到 doc。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    build_contents: list[str] = []
    analysis = {"display_name": "小明", "relationship": "好朋友",
                "expression_rules": ["一次只说一句话"], "memories": [{"slug": "core", "body": "食堂"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        body = json or {}
        if body.get("response_format"):
            content = _json.dumps(analysis, ensure_ascii=False)
        else:
            build_contents.append(body["messages"][0]["content"])
            content = "# 小明 — Persona"
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": content}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    fix = "他不会这样，他其实很细心"
    doc = distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}}, corrections=[fix])
    assert build_contents and "用户纠正：" + fix in build_contents[0]
    assert doc.corrections == [fix]


def test_distill_build_model_override(examples_dir, monkeypatch):
    """配置 [build] 段应覆盖撰写阶段模型（analyze 仍用主模型）。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    build_models: list[str] = []
    analysis = {"display_name": "小明", "relationship": "好朋友", "expression_rules": ["一次只说一句话"]}

    def fake_post(url, headers=None, json=None, timeout=None):
        body = json or {}
        if body.get("response_format"):
            content = _json.dumps(analysis, ensure_ascii=False)
        else:
            build_models.append(body.get("model"))
            content = "# 小明 — Persona"
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": content}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    cfg = {"model": {"base_url": "http://x", "api_key": "k", "model": "cheap"},
           "build": {"base_url": "http://b", "api_key": "bk", "model": "strong-model"}}
    distill(msgs, "小明", cfg)
    assert build_models == ["strong-model"], f"build 阶段应用 [build] 模型，实际 {build_models}"


def test_distill_relationship_summary_flows(examples_dir, monkeypatch):
    """关系总结（arc/essence）应进 PersonaDoc 与 build 请求；记忆带 significance（真实感）。"""
    import json as _json
    msgs = parse_messages(str(examples_dir / "chat.txt"))
    analysis = {
        "display_name": "小明", "relationship": "好朋友",
        "relationship_context": "大学同学。",
        "relationship_arc": "大一军训认识，一起逃过课，毕业各奔东西但每周都聊。",
        "relationship_essence": "他是那种你半夜打电话一定会接的人。",
        "expression_rules": ["一次只说一句话"],
        "memories": [{"slug": "mem/军训", "body": "军训一起偷懒", "quote": "走，翘了",
                      "trigger": "聊军训", "significance": "这是他们熟起来的起点"}],
    }
    build_contents: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        body = json or {}
        if body.get("response_format"):
            content = _json.dumps(analysis, ensure_ascii=False)
        else:
            build_contents.append(body["messages"][0]["content"])
            content = "# 小明 — Persona\n\n## 这段关系 · 一路走来\n大一军训认识。"
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": content}}]}
        return R()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    doc = distill(msgs, "小明", {"model": {"base_url": "http://x", "api_key": "k", "model": "m"}})
    assert doc.relationship_arc == "大一军训认识，一起逃过课，毕业各奔东西但每周都聊。"
    assert doc.relationship_essence == "他是那种你半夜打电话一定会接的人。"
    assert build_contents
    assert "这段关系 · 一路走来" in build_contents[0], "build prompt 应含关系总结段要求"
    assert "significance" in build_contents[0], "记忆的关系意义应进入 build"
    assert "他是那种你半夜打电话一定会接的人" in build_contents[0]
