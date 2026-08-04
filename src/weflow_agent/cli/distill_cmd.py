"""distill：解析中间产物 → PersonaDoc → persona skill 文本。"""
import json
from pathlib import Path

import typer

from ..core.distill import distill, load_config
from ..core.models import Message


def _find_parsed(workdir: Path, name: str) -> Path | None:
    """定位解析中间产物：优先 workdir 根目录，其次 workdir/parsed（默认布局）。"""
    root = Path(workdir) / f"{name}.json"
    if root.exists():
        return root
    parsed = Path(workdir) / "parsed" / f"{name}.json"
    return parsed if parsed.exists() else None


def distill_persona(name: str, workdir: str, config_path: str | None) -> None:
    parsed_path = _find_parsed(Path(workdir), name)
    if parsed_path is None:
        raise typer.BadParameter(f"未找到解析产物 {Path(workdir)/name}.json，请先运行 import")
    msgs = [Message(**m) for m in json.loads(parsed_path.read_text(encoding="utf-8"))]
    config = load_config(config_path)
    doc = distill(msgs, name, config)
    persona_dir = Path(workdir) / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    out = persona_dir / f"{name}.md"
    out.write_text(doc.system_prompt or doc.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"[distill] 已生成 persona -> {out}")
