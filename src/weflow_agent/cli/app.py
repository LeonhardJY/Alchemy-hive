"""CLI 主入口：注册子命令。子命令实现见 import_cmd / distill_cmd / export_cmd。"""
import typer

from .import_cmd import import_chat
from .distill_cmd import distill_persona
from .export_cmd import export_buzz
from ..core.distill import load_config

app = typer.Typer(
    help="weflow-agent: 从微信聊天记录蒸馏人物 AI agent，导出 buzz 快照。",
    no_args_is_help=True,
)

@app.command()
def init(config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件路径")):
    """初始化工作目录，生成配置模板。"""
    typer.echo(f"[init] 配置模板将生成到 {config_path}（M1 占位）")

@app.command("import")
def import_cmd(
    input_path: str = typer.Argument(..., help="WeFlow 导出 JSON 或微信 txt"),
    name: str = typer.Option(..., "--name", help="人物名"),
    out_dir: str = typer.Option("build/parsed", "--out-dir", help="解析产物目录"),
):
    """解析聊天记录 → 结构化消息。"""
    import_chat(input_path, name, out_dir)

@app.command("distill")
def distill_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件"),
):
    """蒸馏 PersonaDoc + persona skill。"""
    distill_persona(name, workdir, load_config(config_path))

@app.command("export")
def export_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
):
    """导出 buzz .agent.json 快照。"""
    export_buzz(name, workdir)

def main() -> None:
    app()

if __name__ == "__main__":
    main()
