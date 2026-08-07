"""CLI 主入口：注册子命令。子命令实现见 import_cmd / distill_cmd / export_cmd。"""
import typer

from .import_cmd import import_chat
from .distill_cmd import distill_persona
from .export_cmd import export_buzz, export_pack
from .blindtest_cmd import run_blindtest
from ..core.distill import load_config
from ..core.llm import LLMError

app = typer.Typer(
    help="alchemy-hive: 从微信聊天记录蒸馏人物 AI agent，导出 buzz 快照。",
    no_args_is_help=True,
    pretty_exceptions_enable=False,  # 用户命令行不渲染巨型 rich traceback（红线：不裸 traceback）
)


def _run_command(fn, *args, **kwargs):
    """执行命令主体：业务/IO 异常（LLMError、ValueError、OSError）统一渲染为
    一句中文错误并退出 1，避免裸 traceback。

    typer 0.24 无 exception_handler 全局钩子，故由可能抛异常的 import/distill/export/blindtest 命令统一走此入口。
    typer.BadParameter 不在捕获范围，仍由 typer 自行渲染。
    """
    try:
        fn(*args, **kwargs)
    except (ValueError, OSError, LLMError) as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1) from e

@app.command("init")
def init_cmd(config_path: str = typer.Option(".alchemy-hive/config.toml", "--config", help="配置文件路径")):
    """初始化：把 config.toml.example 复制为 config.toml（已存在则跳过）。"""
    from pathlib import Path
    p = Path(config_path)
    if p.exists():
        typer.echo(f"[init] 配置已存在：{p}（无需重新生成）")
        return
    example = p.with_name("config.toml.example")
    if not example.exists():
        example = Path(".alchemy-hive/config.toml.example")
    if not example.exists():
        typer.echo(f"[init] 未找到模板 {example}，请确认在项目根目录运行", err=True)
        raise typer.Exit(1)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    typer.echo(f"[init] 已生成配置 {p}，填入 API key 后即可运行 distill")

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
    config_path: str = typer.Option(".alchemy-hive/config.toml", "--config", help="配置文件"),
    profile: str = typer.Option("", "--profile", help="手动画像：性格标签，如 'INTJ 摩羯座 爱吐槽 重感情'（最高优先级）"),
    fix: str = typer.Option(None, "--fix", help="纠正：如 '他不会这样，他其实很细心'（叠加到校正记录）"),
):
    """蒸馏 PersonaDoc + persona skill（支持手动画像与交互校正）。"""
    _run_command(distill_persona, name, workdir, load_config(config_path), profile, fix)

@app.command("export")
def export_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    with_memory: bool = typer.Option(False, "--with-memory", help="导出共同记忆（明文、含真实内容）"),
):
    """导出 buzz .agent.json 快照。"""
    _run_command(export_buzz, name, workdir, with_memory)

@app.command("pack")
def pack_cmd(
    names: str = typer.Option(..., "--names", help="逗号分隔的人物名，如 小明,小红"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    channel: str = typer.Option("#friends", "--channel", help="群组频道名"),
    with_memory: bool = typer.Option(False, "--with-memory", help="导出共同记忆（明文、含真实内容）"),
):
    """批量导出多 agent 快照 + 社群清单。"""
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    if not name_list:
        raise typer.BadParameter("--names 至少需要一个名字")
    _run_command(export_pack, name_list, workdir, channel, with_memory)

@app.command("blindtest")
def blindtest_cmd(
    name: str = typer.Option(..., "--name", help="人物名"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    config_path: str = typer.Option(".alchemy-hive/config.toml", "--config", help="配置文件"),
    n: int = typer.Option(5, "--n", help="抽样片段数"),
):
    """盲测对拍：真实回复 vs agent 接话，人工评分。"""
    _run_command(run_blindtest, name, workdir, load_config(config_path), n)

@app.command("doctor")
def doctor_cmd(config_path: str = typer.Option(".alchemy-hive/config.toml", "--config", help="配置文件路径")):
    """检查配置与端点连通性（GET /models，不发 LLM 请求、不消耗 token）。"""
    from ..core.health import run_doctor
    for line in run_doctor(config_path):
        typer.echo(line)


@app.command("buzz-import")
def buzz_import_cmd(
    name: str = typer.Option("", "--name", help="人物名（不填则导入 build/export 下全部成品）"),
    workdir: str = typer.Option("build", "--workdir", help="工作目录"),
    channel: str = typer.Option(None, "--channel", help="buzz 频道 UUID（不填则读配置 [buzz]）"),
    config_path: str = typer.Option(".alchemy-hive/config.toml", "--config", help="配置文件"),
):
    """一键导入 buzz：打开导出文件夹 + 复制路径；配置齐全时用 buzz-cli 直连建号。高容错，不填名称自动导入全部。"""
    from ..buzz.importing import import_to_buzz, _load_buzz_config
    bz = _load_buzz_config(config_path)
    for line in import_to_buzz(name, workdir, channel or bz["channel"], bz["relay_url"]):
        typer.echo(line)


@app.command("buzz-setup")
def buzz_setup_cmd(
    config_path: str = typer.Option(".alchemy-hive/config.toml", "--config", help="配置文件"),
    channel: str = typer.Option(None, "--channel", help="要存进配置的频道 UUID"),
    relay: str = typer.Option(None, "--relay", help="relay 地址（默认 http://localhost:3000）"),
):
    """开发者引导：检查 buzz-cli/密钥/relay，配置直连建号，把 channel 存进 [buzz] 配置。"""
    from ..buzz.importing import buzz_setup
    for line in buzz_setup(config_path, channel, relay):
        typer.echo(line)


@app.command("gui")
def gui_cmd():
    """启动桌面图形界面（pywebview 玻璃拟态）。"""
    from ..gui.webview_app import run_gui
    run_gui()

def main() -> None:
    app()

if __name__ == "__main__":
    main()
