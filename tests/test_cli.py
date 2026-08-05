import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from weflow_agent.cli.app import app
from weflow_agent.cli.distill_cmd import distill_persona

runner = CliRunner()

def test_cli_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "weflow-agent" in result.output

def test_cli_import_subcommand_exists():
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output


def test_distill_persona_rejects_non_dict_non_str_config(tmp_path):
    # 防御：config 既非 str 也非 dict（如 pathlib.Path）时应抛清晰的 typer.BadParameter
    parsed = tmp_path / "parsed"
    parsed.mkdir(parents=True)
    msg = {"sender": "我", "content": "你好", "timestamp": "2026-01-01 00:00:00"}
    (parsed / "张書源.json").write_text(
        json.dumps([msg], ensure_ascii=False), encoding="utf-8"
    )
    try:
        distill_persona("张書源", str(tmp_path), Path("somewhere/config.toml"))
        assert False, "非 dict 非 str 的 config 应抛 typer.BadParameter"
    except typer.BadParameter as e:
        assert "配置必须是 dict 或配置文件路径" in str(e)
