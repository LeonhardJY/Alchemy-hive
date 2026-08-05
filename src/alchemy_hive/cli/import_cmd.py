"""import：解析聊天记录 → 结构化消息中间产物。"""
import json
from pathlib import Path

import typer

from ..core.parser import parse_messages
from ..core.safe import safe_filename


def import_chat(input_path: str, name: str, out_dir: str) -> None:
    msgs = parse_messages(input_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"{safe_filename(name)}.json"
    out.write_text(json.dumps([m.model_dump() for m in msgs], ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"[import] 解析 {len(msgs)} 条消息 -> {out}")
