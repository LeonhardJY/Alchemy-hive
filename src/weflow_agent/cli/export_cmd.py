"""export：PersonaDoc → buzz .agent.json。"""
import json
from pathlib import Path

import typer

from ..buzz.snapshot import write_snapshot_json
from ..core.models import PersonaDoc


def export_buzz(name: str, workdir: str) -> None:
    persona_path = Path(workdir) / "persona" / f"{name}.md"
    if not persona_path.exists():
        raise typer.BadParameter(f"未找到 persona {persona_path}，请先运行 distill")
    doc = PersonaDoc(name=name, display_name=name, system_prompt=persona_path.read_text(encoding="utf-8"))
    export_dir = Path(workdir) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir))
    typer.echo(f"[export] 已生成 -> {path}")
    typer.echo("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")
