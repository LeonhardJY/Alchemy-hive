"""CLI 主入口：注册子命令。子命令实现见 import_cmd / distill_cmd / export_cmd。"""
from typing import Optional
import typer

app = typer.Typer(
    help="weflow-agent: 从微信聊天记录蒸馏人物 AI agent，导出 buzz 快照。",
    no_args_is_help=True,
)

@app.command()
def init(config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件路径")):
    """初始化工作目录，生成配置模板。"""
    typer.echo(f"[init] 配置模板将生成到 {config_path}（M1 占位）")

@app.command(name="import")
def import_chat(
    input_path: str = typer.Argument(..., help="WeFlow 导出的 JSON 或微信导出 txt"),
    name: str = typer.Option(..., "--name", help="人物名（显示名）"),
    out_dir: str = typer.Option("build/parsed", "--out-dir", help="解析结果输出目录"),
):
    """解析聊天记录 → 结构化消息。"""
    typer.echo(f"[import] 占位: {input_path} -> {name}")

@app.command()
def distill(
    name: str = typer.Option(..., "--name", help="人物名"),
    force: bool = typer.Option(False, "--force", help="强制重新蒸馏"),
):
    """蒸馏 PersonaDoc + persona skill。"""
    typer.echo(f"[distill] 占位: {name}")

@app.command()
def export(
    name: str = typer.Option(..., "--name", help="人物名"),
    out_dir: str = typer.Option("build/export", "--out-dir", help="导出目录"),
):
    """导出 buzz .agent.json 快照。"""
    typer.echo(f"[export] 占位: {name} -> {out_dir}")

def main() -> None:
    app()

if __name__ == "__main__":
    main()
