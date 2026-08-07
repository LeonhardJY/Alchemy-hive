import json
import os
from pathlib import Path
from typer.testing import CliRunner
from alchemy_hive.cli.app import app

runner = CliRunner()

# 与 _write_fake_cfg 写出的配置一致：用于断言请求发往所配端点
_MODEL_CFG = {"base_url": "http://x", "api_key": "k", "model": "m"}


def _fake_llm(monkeypatch):
    """mock alchemy_hive.core.llm.httpx.post，返回假 OpenAI 响应，绕过真实网络。

    两阶段：analyze(json_mode) 返回分析 JSON，build(非 json_mode) 返回 persona Markdown。
    返回捕获到的请求 kwargs（url/headers/json），供测试断言样本发往所配端点。
    """
    import json as _json

    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        body = k.get("json") or {}
        if body.get("response_format"):  # analyze 阶段
            content = _json.dumps({
                "display_name": "小明", "relationship": "好朋友",
                "expression_rules": ["一次只说一句话"],
                "memories": [{"slug": "core", "body": "一起在食堂研究菜单"}],
            }, ensure_ascii=False)
        else:  # build 阶段
            content = "你是小明。\n一次只说一句话。"
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": content}}]}})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    return captured


def _assert_distill_request(captured):
    """锁死"样本发往所配端点"：url 指向 base_url 的 /chat/completions、带 api_key、model 与配置一致。"""
    url = captured["url"]
    assert url.startswith(_MODEL_CFG["base_url"]), url
    assert "/chat/completions" in url, url
    assert _MODEL_CFG["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == _MODEL_CFG["model"]


def _write_fake_cfg(tmp_path):
    """写一份指向假模型的 [model] 配置，使 distill 通过 api_key 校验。"""
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("[model]\nbase_url=\"http://x\"\napi_key=\"k\"\nmodel=\"m\"\n", encoding="utf-8")
    return str(cfg)


def test_e2e_full_pipeline(tmp_path, monkeypatch, examples_dir):
    captured = _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    # import
    r1 = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r1.exit_code == 0, r1.output
    parsed = json.loads((tmp_path / "小明.json").read_text(encoding="utf-8"))
    assert len(parsed) >= 2
    # distill（mock LLM，走假配置，绕过真实网络）
    r2 = runner.invoke(app, ["distill", "--name", "小明", "--workdir", out, "--config", cfg])
    assert r2.exit_code == 0, r2.output
    assert (tmp_path / "persona" / "小明.md").exists()
    _assert_distill_request(captured)
    # export
    r3 = runner.invoke(app, ["export", "--name", "小明", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "export" / "小明.agent.json").exists()
    # 隐私提醒
    assert "脱敏" in r3.output


def test_distill_persists_persona_json_with_memory(tmp_path, monkeypatch, examples_dir):
    captured = _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    r_imp = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r_imp.exit_code == 0, r_imp.output
    r = runner.invoke(app, ["distill", "--name", "小明", "--workdir", out, "--config", cfg])
    assert r.exit_code == 0, r.output
    _assert_distill_request(captured)
    json_path = tmp_path / "persona" / "小明.json"
    assert json_path.exists(), "distill 应持久化完整 PersonaDoc JSON"
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert "system_prompt" in doc and "memory" in doc  # 完整字段


def test_e2e_export_includes_memory_when_opted_in(tmp_path, monkeypatch, examples_dir):
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    r_imp = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r_imp.exit_code == 0, r_imp.output
    r_dis = runner.invoke(app, ["distill", "--name", "小明", "--workdir", out, "--config", cfg])
    assert r_dis.exit_code == 0, r_dis.output
    # 手动注入一条记忆，模拟 LLM 蒸馏产出的记忆（mock LLM 未返回记忆）
    p = tmp_path / "persona" / "小明.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["memory"] = [{"slug": "mem/寺庙", "body": "跟妈妈去寺庙还愿"}]
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    # 默认不含记忆（明文隐私），且有省略提示
    r = runner.invoke(app, ["export", "--name", "小明", "--workdir", out])
    assert r.exit_code == 0, r.output
    snap = json.loads((tmp_path / "export" / "小明.agent.json").read_text(encoding="utf-8"))
    assert snap["memory"]["level"] == "none"
    assert snap["memory"]["entries"] == []
    assert "共同记忆" in r.output and "省略" in r.output
    # 显式 opt-in：--with-memory 才导出
    r2 = runner.invoke(app, ["export", "--name", "小明", "--workdir", out, "--with-memory"])
    assert r2.exit_code == 0, r2.output
    snap2 = json.loads((tmp_path / "export" / "小明.agent.json").read_text(encoding="utf-8"))
    assert snap2["memory"]["level"] == "everything"
    assert snap2["memory"]["entries"][0]["slug"] == "mem/寺庙"


def test_e2e_export_corrupt_json_reports_clear_error(tmp_path):
    out = str(tmp_path)
    # 构造损坏 json（主产物存在但非法）
    (tmp_path / "persona").mkdir(parents=True)
    (tmp_path / "persona" / "小明.json").write_text("{invalid", encoding="utf-8")
    r = runner.invoke(app, ["export", "--name", "小明", "--workdir", out])
    assert r.exit_code != 0, r.output
    assert "损坏" in r.output
    assert "Traceback" not in r.output


def test_e2e_export_schema_mismatch_reports_clear_error(tmp_path):
    out = str(tmp_path)
    # json 合法但缺必填字段 → ValidationError，同样报损坏类错误
    (tmp_path / "persona").mkdir(parents=True)
    (tmp_path / "persona" / "小明.json").write_text("{}", encoding="utf-8")
    r = runner.invoke(app, ["export", "--name", "小明", "--workdir", out])
    assert r.exit_code != 0, r.output
    assert "损坏" in r.output
    assert "Traceback" not in r.output


def test_blindtest_command(monkeypatch, tmp_path, examples_dir):
    # mock 模型接话 + 人工打分输入，走真实 CLI 命令
    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": "走，吃饭"}}]}})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    monkeypatch.setattr("alchemy_hive.cli.blindtest_cmd.input", lambda *a: "4")
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)  # blindtest 需真实 [model] 配置，否则无 key 抛 DistillError
    r_imp = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r_imp.exit_code == 0, r_imp.output
    r = runner.invoke(app, ["blindtest", "--name", "小明", "--workdir", out, "--config", cfg, "--n", "1"])
    assert r.exit_code == 0, r.output
    assert "平均分" in r.output
    # 锁死盲测请求发往所配端点
    assert captured["url"] == _MODEL_CFG["base_url"] + "/chat/completions"
    assert _MODEL_CFG["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == _MODEL_CFG["model"]


def test_blindtest_null_content_does_not_traceback(monkeypatch, tmp_path, examples_dir):
    # 回归 Task A：DeepSeek 等推理模型响应 content: null 时，ask_agent 返回空串，
    # CLI 不裸 traceback、正常跑完打分
    def fake_post(*a, **k):
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": None}}]}})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    monkeypatch.setattr("alchemy_hive.cli.blindtest_cmd.input", lambda *a: "4")
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    r_imp = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r_imp.exit_code == 0, r_imp.output
    r = runner.invoke(app, ["blindtest", "--name", "小明", "--workdir", out, "--config", cfg, "--n", "1"])
    assert r.exit_code == 0, r.output
    assert "agent 接话:" in r.output
    assert "Traceback" not in r.output


def test_blindtest_no_key_reports_clean_error(tmp_path, examples_dir):
    # 无 [model] key：load_config 返回空 dict → ask_agent 抛 DistillError
    # 全局处理应输出一句中文错误并退出 1，绝不渲染裸 traceback
    out = str(tmp_path)
    r_imp = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r_imp.exit_code == 0, r_imp.output
    r = runner.invoke(app, ["blindtest", "--name", "小明", "--workdir", out, "--config", "no-such.toml", "--n", "1"])
    assert r.exit_code != 0, r.output
    assert "Traceback" not in r.output
    assert "未配置模型" in r.output and "API key" in r.output


def test_e2e_init_copies_template(tmp_path):
    """init 把 config.toml.example 复制为 config.toml；已存在则跳过。"""
    from pathlib import Path as _P
    # 用临时目录模拟项目根：造一个 example
    root = tmp_path / "root"
    al = root / ".alchemy-hive"
    al.mkdir(parents=True)
    (al / "config.toml.example").write_text("[model]\nbase_url=\"x\"\napi_key=\"\"\nmodel=\"m\"\n", encoding="utf-8")
    cfg = al / "config.toml"
    r = runner.invoke(app, ["init", "--config", str(cfg)])
    assert r.exit_code == 0, r.output
    assert cfg.exists() and "base_url" in cfg.read_text(encoding="utf-8")
    # 已存在 → 跳过
    r2 = runner.invoke(app, ["init", "--config", str(cfg)])
    assert r2.exit_code == 0 and "已存在" in r2.output


def test_e2e_distill_with_profile_and_fix(tmp_path, monkeypatch, examples_dir):
    """交互式蒸馏：--profile 手动画像 + --fix 校正，都应进产物并持久化。"""
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    r1 = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", "小明", "--out-dir", out])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["distill", "--name", "小明", "--workdir", out, "--config", cfg,
                             "--profile", "INTJ 摩羯座 爱吐槽"])
    assert r2.exit_code == 0, r2.output
    assert "手动画像" in r2.output
    r3 = runner.invoke(app, ["distill", "--name", "小明", "--workdir", out, "--config", cfg, "--fix", "他不会这样"])
    assert r3.exit_code == 0, r3.output
    assert "纠正" in r3.output
    persona = json.loads((tmp_path / "persona" / "小明.json").read_text(encoding="utf-8"))
    assert persona.get("manual_profile") == "INTJ 摩羯座 爱吐槽"
    assert persona.get("corrections") == ["他不会这样"]


def test_export_pack_generates_multiple_agents(tmp_path, monkeypatch, examples_dir):
    _fake_llm(monkeypatch)
    out = str(tmp_path)
    cfg = _write_fake_cfg(tmp_path)
    for nm in ("小明", "小红"):
        r1 = runner.invoke(app, ["import", str(examples_dir / "chat.txt"), "--name", nm, "--out-dir", out])
        assert r1.exit_code == 0, r1.output
        r2 = runner.invoke(app, ["distill", "--name", nm, "--workdir", out, "--config", cfg])
        assert r2.exit_code == 0, r2.output
    r3 = runner.invoke(app, ["pack", "--names", "小明,小红", "--workdir", out])
    assert r3.exit_code == 0, r3.output
    assert (tmp_path / "export" / "小明.agent.json").exists()
    assert (tmp_path / "export" / "小红.agent.json").exists()
    comm = json.loads((tmp_path / "export" / "community.json").read_text(encoding="utf-8"))
    assert len(comm["agents"]) == 2


def test_export_pack_missing_persona_errors(tmp_path):
    out = str(tmp_path)
    r = runner.invoke(app, ["pack", "--names", "不存在的人", "--workdir", out])
    assert r.exit_code != 0
    assert "distill" in r.output


def test_export_pack_corrupt_utf8_reports_distill_hint(tmp_path):
    # 回归：persona JSON 是非法 UTF-8（read_text 抛 UnicodeDecodeError）时，
    # 必须与损坏 JSON 同样提示重新 distill，不能被通用 ValueError 边界吞成编码错误
    out = str(tmp_path)
    (tmp_path / "persona").mkdir(parents=True)
    (tmp_path / "persona" / "小明.json").write_bytes(b"\xff\xfe\x00\x80 invalid")
    r = runner.invoke(app, ["pack", "--names", "小明", "--workdir", out])
    assert r.exit_code != 0, r.output
    assert "distill" in r.output
    assert "Traceback" not in r.output


def test_export_pack_forces_doc_name_to_request_name(tmp_path):
    # 回归：persona/A.json 内容合法但内部 name=B 时，生成的 .agent.json 必须用请求名 A，
    # 否则 community.json 清单会指向不存在的 B.agent.json（幽灵文件）
    out = str(tmp_path)
    (tmp_path / "persona").mkdir(parents=True)
    (tmp_path / "persona" / "A.json").write_text(json.dumps({
        "name": "B",
        "display_name": "B",
        "system_prompt": "你是 B。",
    }, ensure_ascii=False), encoding="utf-8")
    r = runner.invoke(app, ["pack", "--names", "A", "--workdir", out])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "export" / "A.agent.json").exists()
    assert not (tmp_path / "export" / "B.agent.json").exists()
    comm = json.loads((tmp_path / "export" / "community.json").read_text(encoding="utf-8"))
    assert len(comm["agents"]) == 1
    # 清单引用的路径必须真实存在（名称不一致时不指向幽灵文件）
    assert Path(comm["agents"][0]["agentJson"]).exists()


def test_pack_empty_names_reports_clear_error(tmp_path):
    # 回归：--names 过滤后为空列表时直接报错，避免生成空 community.json
    out = str(tmp_path)
    r = runner.invoke(app, ["pack", "--names", ",,", "--workdir", out])
    assert r.exit_code != 0, r.output
    assert "至少需要一个名字" in r.output
    assert not (tmp_path / "export" / "community.json").exists()
    assert "Traceback" not in r.output


def test_e2e_import_missing_file_reports_clean_error(tmp_path):
    # import 一个不存在的文件：FileNotFoundError 应被 CLI 统一错误边界捕获，
    # 输出一句中文错误并退出非 0，绝不裸 traceback
    r = runner.invoke(app, ["import", "no-such-file.json", "--name", "小明", "--out-dir", str(tmp_path)])
    assert r.exit_code != 0, r.output
    assert "Traceback" not in r.output
    assert "错误" in r.output and "文件不存在" in r.output


def test_blindtest_default_out_dir_and_workdir(tmp_path, monkeypatch):
    # import 用默认 out-dir（build/parsed），blindtest 用默认 workdir（build）：
    # 应能找到解析产物并跑到打分阶段（mock httpx + 人工打分输入）
    captured: dict = {}

    def fake_post(*a, **k):
        captured.update(k)
        captured["url"] = a[0]
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"choices": [{"message": {"content": "走，吃饭"}}]}})()

    monkeypatch.setattr("alchemy_hive.core.llm.httpx.post", fake_post)
    monkeypatch.setattr("alchemy_hive.cli.blindtest_cmd.input", lambda *a: "4")
    chat = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples", "chat.txt"))
    monkeypatch.chdir(tmp_path)
    cfg = _write_fake_cfg(tmp_path)  # blindtest 需真实 [model] 配置，否则无 key 抛 DistillError
    r1 = runner.invoke(app, ["import", chat, "--name", "小明"])
    assert r1.exit_code == 0, r1.output
    assert (tmp_path / "build" / "parsed" / "小明.json").exists()
    r2 = runner.invoke(app, ["blindtest", "--name", "小明", "--config", cfg, "--n", "1"])
    assert r2.exit_code == 0, r2.output
    assert "平均分" in r2.output
    # 锁死盲测请求发往所配端点
    assert captured["url"] == _MODEL_CFG["base_url"] + "/chat/completions"
    assert _MODEL_CFG["api_key"] in captured["headers"]["Authorization"]
    assert captured["json"]["model"] == _MODEL_CFG["model"]
