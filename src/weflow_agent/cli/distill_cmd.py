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


def distill_persona(name: str, workdir: str, config: dict | str | None) -> None:
    """蒸馏 PersonaDoc + persona skill。config 可为 dict、config 文件路径或 None。"""
    parsed_path = _find_parsed(Path(workdir), name)
    if parsed_path is None:
        raise typer.BadParameter(f"未找到解析产物 {Path(workdir)/name}.json，请先运行 import")
    msgs = [Message(**m) for m in json.loads(parsed_path.read_text(encoding="utf-8"))]
    if isinstance(config, str):
        cfg = load_config(config)
    elif config is None:
        cfg = {}
    elif isinstance(config, dict):
        cfg = config
    else:
        raise typer.BadParameter(f"配置必须是 dict 或配置文件路径，收到 {type(config).__name__}")
    doc = distill(msgs, name, cfg)
    persona_dir = Path(workdir) / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    out = persona_dir / f"{name}.md"
    out.write_text(doc.system_prompt or doc.model_dump_json(indent=2), encoding="utf-8")
    # 持久化完整 PersonaDoc（含 memory），供 export 恢复
    json_path = persona_dir / f"{name}.json"
    json_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"[distill] 已生成 persona -> {out}")
