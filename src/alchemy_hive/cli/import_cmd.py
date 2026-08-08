"""import：解析聊天记录 → 结构化消息中间产物。"""
import json
from pathlib import Path

import typer

from ..core.parser import parse_messages
from ..core.safe import safe_filename


def import_chat(input_path: str, name: str, out_dir: str, self_aliases: str = "", source: str = "auto") -> None:
    aliases = [a.strip() for a in self_aliases.split(",") if a.strip()] or None
    msgs = parse_messages(input_path, self_aliases=aliases, source=source)
    if not msgs:
        typer.echo("[警告] 解析出 0 条消息，请确认文件是 WeFlow 导出的 JSON 或微信导出的 txt（时间戳+发送者行）", err=True)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"{safe_filename(name)}.json"
    # 紧凑写入：大聊天记录用 indent 会又慢又大
    with out.open("w", encoding="utf-8") as fh:
        json.dump([m.model_dump() for m in msgs], fh, ensure_ascii=False, separators=(",", ":"))
    typer.echo(f"[import] 解析 {len(msgs)} 条消息 -> {out}")
