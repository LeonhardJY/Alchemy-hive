"""buzz 一键导入：高容错（无成品/空名/错名都友好处理）+ 打开文件夹/复制路径 + buzz-cli 直连建号 + setup 引导。"""
import pytest

from alchemy_hive.buzz.importing import import_to_buzz, buzz_setup, _save_buzz_channel, _load_buzz_config


def _prepare(monkeypatch, tmp_path, *names):
    import alchemy_hive.buzz.importing as imp
    export = tmp_path / "export"
    export.mkdir(parents=True, exist_ok=True)
    for n in names:
        (export / f"{n}.agent.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(imp, "_open_folder", lambda p: True)
    monkeypatch.setattr(imp, "_copy_to_clipboard", lambda t: True)
    return imp


def test_import_no_export_dir_friendly(tmp_path):
    """没有 build/export 目录 → 友好提示先蒸馏，不抛异常。"""
    logs = import_to_buzz("小明", str(tmp_path))
    assert any("还没蒸馏过" in l or "开始蒸馏" in l for l in logs)
    assert any("开始蒸馏" in l for l in logs)


def test_import_empty_export_friendly(tmp_path):
    """导出目录存在但无成品 → 友好提示先蒸馏。"""
    (tmp_path / "export").mkdir()
    logs = import_to_buzz("小明", str(tmp_path))
    assert any("空的" in l for l in logs)


def test_import_exact_name(monkeypatch, tmp_path):
    imp = _prepare(monkeypatch, tmp_path, "小明")
    logs = import_to_buzz("小明", str(tmp_path))
    assert any("剪贴板" in l for l in logs)
    assert any("1 个" in l for l in logs), "应只导入匹配的那 1 个"
    assert all(l.startswith("[buzz]") for l in logs)


def test_import_empty_name_imports_all(monkeypatch, tmp_path):
    imp = _prepare(monkeypatch, tmp_path, "小明", "小红")
    logs = import_to_buzz("", str(tmp_path))  # 不填名称 → 全部
    assert any("未填名称" in l and "2 个" in l for l in logs)
    assert any("剪贴板" in l for l in logs)


def test_import_wrong_name_falls_back_all(monkeypatch, tmp_path):
    imp = _prepare(monkeypatch, tmp_path, "小明", "小红")
    logs = import_to_buzz("不存在的人", str(tmp_path))
    assert any("没找到「不存在的人」" in l for l in logs)
    assert any("全部" in l for l in logs)


def test_import_to_buzz_no_channel_skips_direct(monkeypatch, tmp_path):
    imp = _prepare(monkeypatch, tmp_path, "小明")
    logs = import_to_buzz("小明", str(tmp_path))  # 未传 channel
    assert any("--channel" in l for l in logs), "应提示直连建号需要 channel"


def test_import_to_buzz_no_cli_skips_direct(monkeypatch, tmp_path):
    imp = _prepare(monkeypatch, tmp_path, "小明")
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: None)
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)  # 无 buzz-cli
    logs = import_to_buzz("小明", str(tmp_path), channel="chan-123")
    assert any("未检测到 buzz-cli" in l for l in logs)


def test_import_to_buzz_no_key_skips_direct(monkeypatch, tmp_path):
    imp = _prepare(monkeypatch, tmp_path, "小明")
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: "/usr/bin/buzz")
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    monkeypatch.delenv("BUZZ_PRIVATE_KEY", raising=False)
    logs = import_to_buzz("小明", str(tmp_path), channel="chan-123")
    assert any("BUZZ_PRIVATE_KEY" in l for l in logs)


def test_import_to_buzz_draft_create_attempted(monkeypatch, tmp_path):
    """buzz-cli + key + channel 齐备 → 真正发起 draft-create，指令走 stdin。"""
    imp = _prepare(monkeypatch, tmp_path, "小明")
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: "/usr/bin/buzz")
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "nsec-test")
    calls: list = []
    inputs: list = []

    class FakeResult:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(imp.subprocess, "run",
                        lambda cmd, **kw: (calls.append(cmd), inputs.append(kw.get("input")))[1] or FakeResult())
    logs = import_to_buzz("小明", str(tmp_path), channel="chan-123")
    assert calls, "应调用 buzz-cli"
    cmd = calls[0]
    assert cmd[0] == "/usr/bin/buzz" and "draft-create" in cmd
    assert "--channel" in cmd and "chan-123" in cmd
    assert "--display-name" in cmd and "小明" in cmd
    assert "--system-prompt" in cmd and "-" in cmd, "指令应走 stdin"
    assert any("已通过 buzz-cli" in l for l in logs)


def test_import_to_buzz_relay_url_threaded(monkeypatch, tmp_path):
    """配置了 relay_url → draft-create 命令带全局 --relay 参数。"""
    imp = _prepare(monkeypatch, tmp_path, "小明")
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: "/usr/bin/buzz")
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "nsec-test")
    calls: list = []

    class FakeResult:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(imp.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or FakeResult())
    import_to_buzz("小明", str(tmp_path), channel="chan-1", relay_url="http://my-relay:3000")
    assert calls and "--relay" in calls[0] and "http://my-relay:3000" in calls[0]


def test_save_and_load_buzz_config(tmp_path):
    """存 [buzz] channel/relay → 能读回；重复存会替换旧值。"""
    cfg = tmp_path / "cfg.toml"
    _save_buzz_channel(str(cfg), "chan-A", "http://r:3000")
    c = _load_buzz_config(str(cfg))
    assert c["channel"] == "chan-A" and c["relay_url"] == "http://r:3000"
    _save_buzz_channel(str(cfg), "chan-B")
    c2 = _load_buzz_config(str(cfg))
    assert c2["channel"] == "chan-B" and c2["relay_url"] is None, "应替换旧 [buzz] 段"


def test_save_buzz_channel_escapes_special_chars(tmp_path):
    """channel/relay 含引号/反斜杠 → 写出的仍是合法 TOML，能原样读回（不写坏配置）。"""
    cfg = tmp_path / "cfg.toml"
    weird = 'chan-"evil"\\x'
    _save_buzz_channel(str(cfg), weird, 'http://r/"q"')
    c = _load_buzz_config(str(cfg))
    assert c["channel"] == weird
    assert c["relay_url"] == 'http://r/"q"'


def test_save_buzz_channel_does_not_corrupt_other_sections(tmp_path):
    """修复回归：其他段含 [buzz] 字符串时（如 URL），不应损坏配置。"""
    cfg = tmp_path / "cfg.toml"
    # 写一个含 [buzz] 字面量的非 [buzz] 段配置
    cfg.write_text(
        '[model]\n'
        'api_key = "k"\n'
        '\n'
        '[other]\n'
        'relay = "wss://relay.example/[buzz]/ws"\n',
        encoding="utf-8",
    )
    _save_buzz_channel(str(cfg), "chan-new")
    c = _load_buzz_config(str(cfg))
    assert c["channel"] == "chan-new", "应正确写入新 channel"
    # 读回完整配置验证 other 段未被破坏
    from alchemy_hive.core.distill import load_config
    full = load_config(str(cfg))
    assert full.get("model", {}).get("api_key") == "k", "[model] 段应保留"
    assert full.get("other", {}).get("relay") == "wss://relay.example/[buzz]/ws", "[other] 段应保留"


def test_buzz_import_cli_lang_en(tmp_path):
    """buzz-import --lang en → 输出英文文案（不再只有中文）。"""
    from typer.testing import CliRunner
    from alchemy_hive.cli.app import app
    r = CliRunner().invoke(app, ["buzz-import", "--workdir", str(tmp_path), "--lang", "en"])
    assert r.exit_code == 0
    assert "distilled anything" in r.output  # no_build 英文文案


def test_buzz_setup_no_cli(monkeypatch, tmp_path):
    import alchemy_hive.buzz.importing as imp
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: None)
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    lines = buzz_setup(str(tmp_path / "cfg.toml"))
    assert any("未找到 buzz-cli" in l for l in lines)
    assert any("cargo install" in l for l in lines)


def test_buzz_setup_no_key(monkeypatch, tmp_path):
    import alchemy_hive.buzz.importing as imp
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: "/usr/bin/buzz")
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    monkeypatch.delenv("BUZZ_PRIVATE_KEY", raising=False)
    lines = buzz_setup(str(tmp_path / "cfg.toml"))
    assert any("BUZZ_PRIVATE_KEY" in l for l in lines)
    assert any("nsec" in l for l in lines)


def test_buzz_setup_relay_fails(monkeypatch, tmp_path):
    import alchemy_hive.buzz.importing as imp
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: "/usr/bin/buzz")
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "nsec-test")

    class FakeErr:
        returncode = 1
        stdout = ""
        stderr = "cannot connect"

    monkeypatch.setattr(imp.subprocess, "run", lambda *a, **k: FakeErr())
    lines = buzz_setup(str(tmp_path / "cfg.toml"))
    assert any("连接 relay 失败" in l for l in lines)
    assert any("localhost:3000" in l for l in lines)


def test_buzz_setup_success_saves_channel(monkeypatch, tmp_path):
    """buzz-cli + key + relay 齐备 → 列出频道并保存 channel 配置。"""
    import alchemy_hive.buzz.importing as imp
    monkeypatch.setattr(imp, "_find_buzz_cli", lambda: "/usr/bin/buzz")
    monkeypatch.setattr(imp, "_detect_desktop_relay", lambda: None)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "nsec-test")

    class FakeOk:
        returncode = 0
        stdout = '[{"id":"chan-9","name":"朋友群"},{"id":"chan-3","name":"工作群"}]'
        stderr = ""

    monkeypatch.setattr(imp.subprocess, "run", lambda *a, **k: FakeOk())
    cfg = str(tmp_path / "cfg.toml")
    lines = buzz_setup(cfg, channel="chan-9")
    assert any("2 个频道" in l for l in lines)
    assert any("朋友群" in l for l in lines)
    assert any("已把 channel=chan-9" in l for l in lines)
    assert _load_buzz_config(cfg)["channel"] == "chan-9"
