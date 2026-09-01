"""distill：解析中间产物 → PersonaDoc → persona skill 文本。"""
import json
from pathlib import Path

import typer

from ..core.distill import distill, distill_incremental, load_config
from ..core.models import Message, PersonaDoc
from ..core.safe import safe_filename


def _find_parsed(workdir: Path, name: str) -> Path | None:
    """定位解析中间产物：优先 workdir 根目录，其次 workdir/parsed（默认布局）。"""
    safe = safe_filename(name)
    root = Path(workdir) / f"{safe}.json"
    if root.exists():
        return root
    parsed = Path(workdir) / "parsed" / f"{safe}.json"
    return parsed if parsed.exists() else None


def _load_existing_persona(workdir: str, name: str) -> PersonaDoc | None:
    """加载已有的 persona（如果存在）。"""
    safe = safe_filename(name)
    persona_json_path = Path(workdir) / "persona" / f"{safe}.json"
    if persona_json_path.exists():
        try:
            return PersonaDoc.model_validate(json.loads(persona_json_path.read_text(encoding="utf-8")))
        except Exception:
            return None
    return None


def distill_persona(name: str, workdir: str, config: dict | str | None,
                    manual_profile: str = "", fix: str | None = None,
                    incremental: bool = False) -> None:
    """蒸馏 PersonaDoc + persona skill。

    incremental: 增量模式，基于已有 persona + 新消息合并。
    """
    safe = safe_filename(name)
    parsed_path = _find_parsed(Path(workdir), name)
    if parsed_path is None:
        raise typer.BadParameter(f"未找到解析产物 {Path(workdir)/safe}.json，请先运行 import")
    msgs = [Message(**m) for m in json.loads(parsed_path.read_text(encoding="utf-8"))]
    if isinstance(config, str):
        cfg = load_config(config)
    elif config is None:
        cfg = {}
    elif isinstance(config, dict):
        cfg = config
    else:
        raise typer.BadParameter(f"配置必须是 dict 或配置文件路径，收到 {type(config).__name__}")

    # 交互校正：读已有 persona 的 corrections + manual_profile 并累积
    existing_doc = _load_existing_persona(workdir, name)
    existing_manual = ""
    corrections: list[str] = []
    if existing_doc:
        corrections = list(existing_doc.corrections or [])
        existing_manual = existing_doc.manual_profile or ""
    if fix:
        corrections.append(fix)
    manual = manual_profile or existing_manual

    # 增量模式
    if incremental and existing_doc:
        typer.echo(f"[distill] 增量模式：基于已有 persona 合并新消息")
        doc = distill_incremental(msgs, name, cfg, existing_doc,
                                  manual_profile=manual, corrections=corrections)
    else:
        doc = distill(msgs, name, cfg, manual_profile=manual, corrections=corrections)

    persona_dir = Path(workdir) / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    out = persona_dir / f"{safe}.md"
    out.write_text(doc.system_prompt or doc.model_dump_json(indent=2), encoding="utf-8")
    json_path = persona_dir / f"{safe}.json"
    json_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"[distill] 已生成 persona -> {out}")
    if manual_profile:
        typer.echo(f"[distill] 已套用手动画像：{manual_profile}")
    if fix:
        typer.echo(f"[distill] 已应用纠正 #{len(corrections)}：{fix}")
