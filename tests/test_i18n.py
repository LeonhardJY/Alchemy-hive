"""GUI 双语化测试：_build_html / run_pipeline / import_to_buzz / 错误翻译。"""
import json

from alchemy_hive.gui.webview_app import _build_html, _tr_error
from alchemy_hive.gui.actions import run_pipeline
from alchemy_hive.buzz.importing import import_to_buzz


def test_build_html_zh_keeps_chinese():
    html = _build_html("zh")
    assert "把微信聊天蒸馏成 AI 朋友" in html
    assert "window.T =" in html
    assert '"start": "开始蒸馏"' in html
    assert '<option value="zh" selected>' in html


def test_build_html_en_translates_static_and_js():
    html = _build_html("en")
    assert "Distill your WeChat chats into AI friends" in html
    assert "把微信聊天蒸馏成 AI 朋友" not in html
    assert '<html lang="en">' in html
    assert '"start": "Start distillation"' in html
    assert '<option value="en" selected>' in html


def test_build_html_en_no_leftover_visible_chinese():
    """英文构建不应残留可见中文文案。"""
    html = _build_html("en")
    for zh in [
        "把微信聊天蒸馏", "浏览文件", "开始蒸馏", "导出共同记忆",
        "自动识别（推荐）", "你的昵称（可选）", "运行后在这里",
        "导入到 buzz · 打开文件夹并复制路径", "开发者进阶",
        "通义千问（阿里云）", "豆包（火山方舟）",
    ]:
        assert zh not in html, f"英文界面残留中文：{zh}"


def test_build_html_en_success_banner_fully_translated():
    """回归：短词（导入buzz）不得先于整句替换，否则成功横幅残留中文。"""
    html = _build_html("en")
    assert "一键装进 buzz" not in html
    assert "往下拉到" not in html
    assert "scroll to “Import to buzz”" in html


def test_lang_switch_label_and_position():
    en = _build_html("en")
    zh = _build_html("zh")
    # 标签：英文界面写 Language，中文界面写 语言（只看可见控件，不看 CSS 注释）
    assert ">Language</label>" in en
    assert ">语言</label>" in zh
    # 右上角固定的独立控件 + 两种语言选项都在
    assert '<div class="lang-switch">' in en
    assert 'id="lang_sel"' in en
    assert '<option value="zh"' in en and '<option value="en"' in en
    assert '<option value="en" selected>' in en
    assert '<option value="zh" selected>' in zh


def _mock_llm(monkeypatch):
    def fake_post(*a, **k):
        body = k.get("json") or {}
        if body.get("response_format"):
            content = json.dumps({
                "display_name": "小明", "relationship": "好朋友",
                "expression_rules": ["一次只说一句话"],
                "memories": [{"slug": "core", "body": "一起研究菜单"}],
            }, ensure_ascii=False)
        else:
            content = "你是小明。\n一次只说一句话。"
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": content}}]},
        })()
    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)


def test_run_pipeline_english_logs(monkeypatch, tmp_path, examples_dir):
    _mock_llm(monkeypatch)
    logs = run_pipeline(
        str(examples_dir / "chat.txt"), "小明",
        {"base_url": "http://x", "api_key": "k", "model": "m"},
        str(tmp_path), lang="en",
    )
    assert logs[0].startswith("[import] Parsed")
    assert any(l.startswith("[distill] Calling") for l in logs)
    assert any(l.startswith("[export] Generated") for l in logs)
    assert not any("条消息" in l for l in logs)


def test_import_to_buzz_english_logs(monkeypatch, tmp_path):
    # 避免真实打开文件夹/写剪贴板
    monkeypatch.setattr("alchemy_hive.buzz.importing._open_folder", lambda p: True)
    monkeypatch.setattr("alchemy_hive.buzz.importing._copy_to_clipboard", lambda t: True)
    export_dir = tmp_path / "export"
    export_dir.mkdir(parents=True)
    (export_dir / "小明.agent.json").write_text('{"definition": {"systemPrompt": "x"}}', encoding="utf-8")
    logs = import_to_buzz("小明", str(tmp_path), lang="en")
    assert any("[buzz]" in l for l in logs)
    assert any("Copied" in l for l in logs)
    assert not any("剪贴板" in l for l in logs)


def test_tr_error_english():
    assert _tr_error("文件不存在: x.txt", "en") == "File not found: x.txt"
    assert _tr_error("未配置模型 API key，请先配置", "en").startswith("No model API key configured")
    assert _tr_error("LLM 蒸馏失败（分析阶段）", "en").startswith("LLM distillation failed")
    # 中文界面不翻译
    assert _tr_error("文件不存在: x.txt", "zh") == "文件不存在: x.txt"


def test_set_lang_updates_and_returns():
    """set_lang 只更新语言并立即返回 True（重载延迟到调用返回后，避免销毁回调表）。"""
    from alchemy_hive.gui.webview_app import Api
    api = Api("zh")
    assert api.set_lang("en") is True
    assert api.lang == "en"
    api.set_lang("en")   # 同语言不重复调度
    assert api.lang == "en"
    # _GUI_WINDOW 为 None 时 _apply_lang 应安全空操作
    api._apply_lang()
