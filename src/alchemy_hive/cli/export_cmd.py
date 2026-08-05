"""export：PersonaDoc → buzz .agent.json。"""
import json
from pathlib import Path

import typer
from pydantic import ValidationError

from ..buzz.snapshot import write_snapshot_json
from ..core.models import PersonaDoc
from ..core.safe import safe_filename


def export_buzz(name: str, workdir: str, with_memory: bool = False) -> None:
    safe = safe_filename(name)
    json_path = Path(workdir) / "persona" / f"{safe}.json"
    md_path = Path(workdir) / "persona" / f"{safe}.md"
    if json_path.exists():
        # 优先从完整 PersonaDoc 恢复（含 memory）
        try:
            doc = PersonaDoc.model_validate(json.loads(json_path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            # 损坏 json（含非法 UTF-8 编码）是主产物问题：明确报错让用户重新蒸馏，不回退 md
            raise typer.BadParameter(
                f"persona/{safe}.json 损坏或格式不符，请删除后重新运行 distill"
            )
    elif md_path.exists():
        # 兼容旧产物：只有 md 时回退为仅 system_prompt
        doc = PersonaDoc(name=name, display_name=name, system_prompt=md_path.read_text(encoding="utf-8"))
    else:
        raise typer.BadParameter(f"未找到 persona {md_path}，请先运行 distill")
    if doc.memory and not with_memory:
        typer.echo(
            f"[提醒] 已省略 {len(doc.memory)} 条共同记忆（记忆为明文、含真实内容，默认不含；"
            "如需导出请加 --with-memory）"
        )
    export_dir = Path(workdir) / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir), include_memory=with_memory)
    typer.echo(f"[export] 已生成 -> {path}")
    typer.echo("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")


def export_pack(names: list[str], workdir: str, channel: str = "#friends", with_memory: bool = False) -> str:
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
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            # 损坏 json（含非法 UTF-8 编码）是主产物问题：明确报错让用户重新蒸馏
            raise typer.BadParameter(
                f"persona/{safe_filename(name)}.json 损坏或格式不符，请删除后重新运行 distill"
            )
        # 强制统一 name 为请求名：保证生成的 .agent.json 文件名与 community.json 清单路径一致
        # （persona 内部 name 可能是 LLM 蒸馏时误写的别名，不能让它决定文件名）
        doc.name = name
        write_snapshot_json(doc, str(export_dir), include_memory=with_memory)
    if with_memory:
        typer.echo("[提醒] 已导出共同记忆（明文、含真实内容），分享前请自行脱敏。")
    comm = build_community(names, str(export_dir), channel)
    comm_path = export_dir / "community.json"
    comm_path.write_text(json.dumps(comm, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"[export pack] 已生成 {len(names)} 个 agent + 社群清单 -> {comm_path}")
    return str(comm_path)
