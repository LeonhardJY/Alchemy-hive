"""GUI 动作管线的纯函数测试（mock LLM，不走真实网络）。"""
import json

import pytest

from alchemy_hive.gui.actions import run_pipeline
from alchemy_hive.core.distill import DistillError

MODEL_CONFIG = {"base_url": "http://x", "api_key": "k", "model": "m"}


@pytest.fixture
def mock_llm(monkeypatch):
    """mock alchemy_hive.core.llm.httpx.post，返回假 OpenAI 响应，绕过真实网络。

    返回捕获到的请求 kwargs（url/headers/json），供测试断言样本发往所配端点。
    """

    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        payload = {
            "display_name": "小明",
            "relationship": "好朋友",
            "expression_rules": ["一次只说一句话"],
            "system_prompt": "你是小明。",
        }
        return type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {
                    "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]
                },
            },
        )()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    return captured


def _assert_request_matches_config(captured, cfg):
    """锁死"样本发往所配端点"：url/auth/model 必须与传入配置一致。"""
    url = captured["url"]
    assert url.startswith(cfg["base_url"]), url
    assert "/chat/completions" in url, url
    assert cfg["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == cfg["model"]


def test_gui_actions_pipeline(mock_llm, tmp_path, examples_dir):
    logs = run_pipeline(
        str(examples_dir / "chat.txt"),
        "小明",
        MODEL_CONFIG,
        str(tmp_path),
    )
    assert any("import" in l for l in logs)
    assert any("distill" in l for l in logs)
    assert (tmp_path / "export" / "小明.agent.json").exists()
    _assert_request_matches_config(mock_llm, MODEL_CONFIG)


def test_gui_actions_pipeline_writes_parsed_json(mock_llm, tmp_path, examples_dir):
    run_pipeline(
        str(examples_dir / "chat.txt"),
        "小明",
        MODEL_CONFIG,
        str(tmp_path),
    )
    parsed_path = tmp_path / "parsed" / "小明.json"
    assert parsed_path.exists(), "管线应把解析产物写入 parsed/{name}.json"
    msgs = json.loads(parsed_path.read_text(encoding="utf-8"))
    assert isinstance(msgs, list) and len(msgs) > 0
    assert "sender" in msgs[0] and "content" in msgs[0] and "timestamp" in msgs[0]


def test_gui_actions_no_key_raises(examples_dir, tmp_path):
    with pytest.raises(DistillError):
        run_pipeline(str(examples_dir / "chat.txt"), "小明", {}, str(tmp_path))


def test_gui_actions_pipeline_streams_logs_and_shows_model(mock_llm, tmp_path, examples_dir):
    """on_log 回调逐行推送；日志包含实际调用的模型端点（LLM 透明化）。"""
    received: list[str] = []
    logs = run_pipeline(
        str(examples_dir / "chat.txt"),
        "小明",
        MODEL_CONFIG,
        str(tmp_path),
        on_log=received.append,
    )
    assert received == logs, "on_log 应逐行收到与返回日志一致的内容"
    assert any(l.startswith("[distill] 调用模型") and "http://x" in l for l in logs)
    assert len(logs) >= 6


def test_js_api_has_no_introspected_window():
    """回归：js_api 实例不能持有 Window/native 等非可调用对象属性。

    pywebview 会用 dir()/getattr() 递归枚举 js_api 整个对象图来生成 JS 桥接表；
    若实例上挂着 Window，会把递归拖入 window.native 的 COM 无障碍对象图 → RecursionError → 窗口无法加载。
    """
    import inspect
    from alchemy_hive.gui.webview_app import Api

    def walk(obj, base="", depth=0):
        assert depth < 500, f"递归枚举 js_api 对象图过深（{base}）——与窗口无法加载同源"
        for name in dir(obj):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(obj, name)
            except Exception:
                continue
            full = f"{base}.{name}" if base else name
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                continue
            if not callable(attr) and hasattr(attr, "__module__"):
                walk(attr, full, depth + 1)

    walk(Api())  # 不抛异常即通过
