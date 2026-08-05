"""export：PersonaDoc → buzz .agent.json。"""
import json
from pathlib import Path

import typer

from ..buzz.snapshot import write_snapshot_json
from ..core.models import PersonaDoc


def export_buzz(name: str, workdir: str) -> None:
    json_path = Path(workdir) / "persona" / f"{name}.json"
    md_path = Path(workdir) / "persona" / f"{name}.md"
    if json_path.exists():
        # 优先从完整 PersonaDoc 恢复（含 memory）
        doc = PersonaDoc.model_validate(json.loads(json_path.read_text(encoding="utf-8")))
    elif md_path.exists():
        # 兼容旧产物：只有 md 时回退为仅 system_prompt
        doc = PersonaDoc(name=name, display_name=name, system_prompt=md_path.read_text(encoding="utf-8"))
    else:
        raise typer.BadParameter(f"未找到 persona {md_path}，请先运行 distill")
    export_dir = Path(workdir) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir))
    typer.echo(f"[export] 已生成 -> {path}")
    typer.echo("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")
