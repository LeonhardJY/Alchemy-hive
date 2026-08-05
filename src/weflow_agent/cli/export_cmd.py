"""export：PersonaDoc → buzz .agent.json。"""
import json
from pathlib import Path

import typer
from pydantic import ValidationError

from ..buzz.snapshot import write_snapshot_json
from ..core.models import PersonaDoc
from ..core.safe import safe_filename


def export_buzz(name: str, workdir: str) -> None:
    safe = safe_filename(name)
    json_path = Path(workdir) / "persona" / f"{safe}.json"
    md_path = Path(workdir) / "persona" / f"{safe}.md"
    if json_path.exists():
        # 优先从完整 PersonaDoc 恢复（含 memory）
        try:
            doc = PersonaDoc.model_validate(json.loads(json_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError):
            # 损坏 json 是主产物问题：明确报错让用户重新蒸馏，不回退 md
            raise typer.BadParameter(
                f"persona/{safe}.json 损坏或格式不符，请删除后重新运行 distill"
            )
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


def export_pack(names: list[str], workdir: str, channel: str = "#friends") -> str:
    """批量导出多 agent 的 .agent.json + 社群清单 community.json，返回 community.json 路径。"""
    from ..core.community import build_community
    export_dir = Path(workdir) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        persona_path = Path(workdir) / "persona" / f"{safe_filename(name)}.json"
        if not persona_path.exists():
            raise typer.BadParameter(
                f"未找到 {name} 的蒸馏产物 {persona_path}，请先运行 import + distill")
        try:
            doc = PersonaDoc.model_validate(json.loads(persona_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError):
            # 损坏 json 是主产物问题：明确报错让用户重新蒸馏
            raise typer.BadParameter(
                f"persona/{safe_filename(name)}.json 损坏或格式不符，请删除后重新运行 distill"
            )
        write_snapshot_json(doc, str(export_dir))
    comm = build_community(names, str(export_dir), channel)
    comm_path = export_dir / "community.json"
    comm_path.write_text(json.dumps(comm, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"[export pack] 已生成 {len(names)} 个 agent + 社群清单 -> {comm_path}")
    return str(comm_path)
