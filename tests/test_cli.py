from typer.testing import CliRunner
from weflow_agent.cli.app import app

runner = CliRunner()

def test_cli_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "weflow-agent" in result.output

def test_cli_import_subcommand_exists():
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
