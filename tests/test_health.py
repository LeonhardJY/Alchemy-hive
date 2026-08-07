"""doctor 自检：不发 LLM 请求即可排查配置与国内网络连通性。"""
import httpx

from alchemy_hive.core.health import run_doctor


def test_doctor_missing_config(tmp_path):
    lines = run_doctor(str(tmp_path / "nope.toml"))
    assert any("未找到配置文件" in l for l in lines)


def test_doctor_missing_fields(tmp_path):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("", encoding="utf-8")  # 空配置 → model 段缺失
    lines = run_doctor(str(cfg))
    assert any("配置缺失" in l for l in lines)
    assert any("未设置" in l for l in lines)


def test_doctor_endpoint_reachable_401(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text('[model]\nbase_url="https://api.deepseek.com/v1"\napi_key="k"\nmodel="m"\n', encoding="utf-8")

    def fake_get(url, timeout=None):
        return type("R", (), {"status_code": 401})()

    monkeypatch.setattr("alchemy_hive.core.health.httpx.get", fake_get)
    lines = run_doctor(str(cfg))
    assert any("可达" in l and "401" in l for l in lines), "\n".join(lines)


def test_doctor_connect_error_hints_domestic(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text('[model]\nbase_url="https://api.openai.com/v1"\napi_key="k"\nmodel="gpt-5.5"\n', encoding="utf-8")

    def fake_get(url, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("alchemy_hive.core.health.httpx.get", fake_get)
    lines = run_doctor(str(cfg))
    assert any("无法连接" in l for l in lines)
    assert any("国内网络" in l for l in lines), "应提示用国内直连模型"


def test_doctor_cli_command(tmp_path):
    from typer.testing import CliRunner
    from alchemy_hive.cli.app import app

    r = CliRunner().invoke(app, ["doctor", "--config", str(tmp_path / "nope.toml")])
    assert r.exit_code == 0
    assert "未找到配置文件" in r.output
