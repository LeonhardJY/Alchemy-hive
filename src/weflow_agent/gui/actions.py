"""GUI 复用的蒸馏动作：把 import→distill→export 串成一个可测试的管线。"""
import json
from pathlib import Path

from ..core.distill import distill, DistillError
from ..core.parser import parse_messages
from ..buzz.snapshot import write_snapshot_json


def run_pipeline(chat_path: str, name: str, model_config: dict, workdir: str) -> list[str]:
    """执行完整蒸馏管线，返回步骤日志。model_config 形如 {"base_url","api_key","model"}。"""
    logs: list[str] = []
    root = Path(workdir)

    parsed_dir = root / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    msgs = parse_messages(chat_path)
    logs.append(f"[import] 解析 {len(msgs)} 条消息")
    parsed_path = parsed_dir / f"{name}.json"
    parsed_path.write_text(
        json.dumps([m.model_dump() for m in msgs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logs.append(f"[import] 已写 parsed/{name}.json")

    cfg = {"model": model_config}
    doc = distill(msgs, name, cfg)
    logs.append("[distill] 蒸馏完成")

    persona_dir = root / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / f"{name}.md").write_text(doc.system_prompt, encoding="utf-8")
    (persona_dir / f"{name}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    logs.append(f"[distill] 已写 persona/{name}.md + .json")

    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir))
    logs.append(f"[export] 已生成 {path}")
    logs.append("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")
    return logs
