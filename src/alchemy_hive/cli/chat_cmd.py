"""chat：终端交互式聊天测试，验证蒸馏出的 persona 效果。"""
from pathlib import Path

import typer

from ..core.chat import create_session
from ..core.safe import safe_filename
from .distill_cmd import _find_parsed


def run_chat(name: str, workdir: str, config: dict) -> None:
    """终端交互式聊天：加载 persona，循环 input → LLM → print。"""
    safe = safe_filename(name)
    persona_path = Path(workdir) / "persona" / f"{safe}.json"
    if not persona_path.exists():
        persona_md = Path(workdir) / "persona" / f"{safe}.md"
        if not persona_md.exists():
            raise typer.BadParameter(f"未找到 persona {persona_path}，请先运行 distill")
        # 兼容旧产物：只有 md 时读取作为 system_prompt
        from ..core.models import PersonaDoc
        doc = PersonaDoc(name=name, display_name=name, system_prompt=persona_md.read_text(encoding="utf-8"))
        from ..core.chat import ChatSession
        session = ChatSession(system_prompt=doc.system_prompt, config=config, name=name)
    else:
        session = create_session(str(persona_path), config)

    typer.echo(f"与 {session.name} 的对话（输入 q 退出）\n")
    while True:
        try:
            user_input = typer.prompt("你")
        except (EOFError, typer.Abort):
            typer.echo("\n再见！")
            break
        if user_input.strip().lower() in ("q", "quit", "exit"):
            typer.echo("再见！")
            break
        try:
            reply = session.send(user_input)
            typer.echo(f"\n{session.name}：{reply}\n")
        except Exception as e:
            typer.echo(f"\n[错误] {e}\n")
