"""CLI 主入口：注册子命令。子命令实现见 import_cmd / distill_cmd / export_cmd。"""
import typer

from .import_cmd import import_chat
from .distill_cmd import distill_persona
from .export_cmd import export_buzz, export_pack
from .blindtest_cmd import run_blindtest
from ..core.distill import load_config, DistillError

app = typer.Typer(
    help="weflow-agent: 从微信聊天记录蒸馏人物 AI agent，导出 buzz 快照。",
    no_args_is_help=True,
    pretty_exceptions_enable=False,  # 用户命令行不渲染巨型 rich traceback（红线：不裸 traceback）
)


def _run_command(fn, *args, **kwargs):
    """执行命令主体：业务/IO 异常（DistillError、FileNotFoundError、ValueError、OSError）统一渲染为
    一句中文错误并退出 1，避免裸 traceback。

    typer 0.24 无 exception_handler 全局钩子，故由可能抛异常的 import/distill/export/blindtest 命令统一走此入口。
    typer.BadParameter 不在捕获范围，仍由 typer 自行渲染。
    """
    try:
        fn(*args, **kwargs)
    except (FileNotFoundError, ValueError, OSError, DistillError) as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1) from e

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
    _run_command(import_chat, input_path, name, out_dir)

@app.command("distill")
def distill_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件"),
):
    """蒸馏 PersonaDoc + persona skill。"""
    _run_command(distill_persona, name, workdir, load_config(config_path))

@app.command("export")
def export_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
):
    """导出 buzz .agent.json 快照。"""
    _run_command(export_buzz, name, workdir)

@app.command("pack")
def pack_cmd(
    names: str = typer.Option(..., "--names", help="逗号分隔的人物名，如 张書源,张鹏博"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    channel: str = typer.Option("#friends", "--channel", help="群组频道名"),
):
    """批量导出多 agent 快照 + 社群清单。"""
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not name_list:
        raise typer.BadParameter("--names 至少需要一个名字")
    _run_command(export_pack, name_list, workdir, channel)

@app.command("blindtest")
def blindtest_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    config_path: str = typer.Option(".weflow-agent/config.toml", "--config", help="配置文件"),
    n: int = typer.Option(5, "--n", help="抽样片段数"),
):
    """盲测对拍：真实回复 vs agent 接话，人工评分。"""
    _run_command(run_blindtest, name, workdir, load_config(config_path), n)

@app.command("gui")
def gui_cmd():
    """启动桌面图形界面（pywebview 玻璃拟态）。"""
    from ..gui.webview_app import run_gui
    run_gui()

def main() -> None:
    app()

if __name__ == "__main__":
    main()
