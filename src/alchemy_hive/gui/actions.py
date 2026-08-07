"""GUI 复用的蒸馏动作：把 import→distill→export 串成一个可测试的管线。"""
import json
from pathlib import Path

from ..core.distill import distill
from ..core.parser import parse_messages
from ..core.safe import safe_filename
from ..buzz.snapshot import write_snapshot_json


def run_pipeline(
    chat_path: str,
    name: str,
    model_config: dict,
    workdir: str,
    with_memory: bool = False,
    on_log=None,
    manual_profile: str = "",
) -> list[str]:
    """执行完整蒸馏管线，返回步骤日志。model_config 形如 {"base_url","api_key","model"}。

    on_log 可选回调：每产生一行日志即调用（GUI 用于实时刷新）；None 则只收集不推送。
    manual_profile：用户手动画像（性格标签，最高优先级）。
    """
    logs: list[str] = []

    def emit(line: str) -> None:
        logs.append(line)
        if on_log:
            try:
                on_log(line)
            except Exception:
                pass

    root = Path(workdir)
    safe = safe_filename(name)

    parsed_dir = root / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    msgs = parse_messages(chat_path)
    if not msgs:
        raise ValueError("解析出 0 条消息，请确认文件是 WeFlow 导出的 JSON 或微信导出的 txt（时间戳+发送者行）")
    emit(f"[import] 解析 {len(msgs)} 条消息")
    parsed_path = parsed_dir / f"{safe}.json"
    # 紧凑写入：大聊天记录用 indent 会又慢又大
    with parsed_path.open("w", encoding="utf-8") as fh:
        json.dump([m.model_dump() for m in msgs], fh, ensure_ascii=False, separators=(",", ":"))
    emit(f"[import] 已写 parsed/{safe}.json")

    cfg = {"model": model_config}
    emit(
        f"[distill] 调用模型 {model_config.get('model', '?')} @ "
        f"{model_config.get('base_url', '?')}/chat/completions"
    )
    if manual_profile:
        emit(f"[distill] 手动画像：{manual_profile}")
    doc = distill(msgs, name, cfg, manual_profile=manual_profile)
    emit("[distill] 蒸馏完成")

    persona_dir = root / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / f"{safe}.md").write_text(doc.system_prompt, encoding="utf-8")
    (persona_dir / f"{safe}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    emit(f"[distill] 已写 persona/{safe}.md + .json")

    if doc.memory and not with_memory:
        emit(
            f"[提醒] 已省略 {len(doc.memory)} 条共同记忆（记忆为明文、含真实内容，默认不含；"
            "如需导出请勾选「导出共同记忆」）"
        )
    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir), include_memory=with_memory)
    emit(f"[export] 已生成 {path}")
    emit("[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。")
    return logs
