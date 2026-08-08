"""GUI 复用的蒸馏动作：把 import→distill→export 串成一个可测试的管线。"""
import json
from pathlib import Path

from ..core.distill import distill
from ..core.parser import parse_messages
from ..core.safe import safe_filename
from ..buzz.snapshot import write_snapshot_json

# 管线日志文案（GUI 按语言输出；默认中文与历史一致，测试锁定）
_L = {
    "zh": {
        "parsed": "[import] 解析 {n} 条消息",
        "parsed_written": "[import] 已写 parsed/{safe}.json",
        "calling": "[distill] 调用模型 {model} @ {url}/chat/completions",
        "profile": "[distill] 手动画像：{profile}",
        "done": "[distill] 蒸馏完成",
        "persona_written": "[distill] 已写 persona/{safe}.md + .json",
        "memory_skipped": "[提醒] 已省略 {n} 条共同记忆（记忆为明文、含真实内容，默认不含；如需导出请勾选「导出共同记忆」）",
        "export_written": "[export] 已生成 {path}",
        "privacy": "[提醒] 产物含真实聊天内容，分享到 GitHub/他人前请自行脱敏。",
        "empty_error": "解析出 0 条消息，请确认文件是支持的导出格式（微信/Telegram/WhatsApp/Instagram/Facebook 的 JSON 或 txt）",
    },
    "en": {
        "parsed": "[import] Parsed {n} messages",
        "parsed_written": "[import] Wrote parsed/{safe}.json",
        "calling": "[distill] Calling {model} @ {url}/chat/completions",
        "profile": "[distill] Manual profile: {profile}",
        "done": "[distill] Distillation complete",
        "persona_written": "[distill] Wrote persona/{safe}.md + .json",
        "memory_skipped": "[Reminder] Skipped {n} shared memories (plaintext & personal — hidden by default; tick “Export memories” to include)",
        "export_written": "[export] Generated {path}",
        "privacy": "[Reminder] Output contains real chat content — sanitize before sharing.",
        "empty_error": "Parsed 0 messages — check the file is a supported export (WeChat/Telegram/WhatsApp/Instagram/Facebook JSON or txt)",
    },
}


def _t(lang: str, key: str, **kw) -> str:
    return _L.get(lang, _L["zh"])[key].format(**kw)


def run_pipeline(
    chat_path: str,
    name: str,
    model_config: dict,
    workdir: str,
    with_memory: bool = False,
    on_log=None,
    manual_profile: str = "",
    self_name: str = "",
    source: str = "auto",
    lang: str = "zh",
) -> list[str]:
    """执行完整蒸馏管线，返回步骤日志。model_config 形如 {"base_url","api_key","model"}。

    on_log 可选回调：每产生一行日志即调用（GUI 用于实时刷新）；None 则只收集不推送。
    manual_profile：用户手动画像（性格标签，最高优先级）。
    self_name：你在对话里的昵称（逗号分隔），用于把你自己归一化为『我』。
    source：导出平台（auto 自动识别，或 weflow/telegram/whatsapp/meta 等）。
    lang：日志语言（zh/en）。
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
    self_aliases = [a.strip() for a in self_name.split(",") if a.strip()] or None
    msgs = parse_messages(chat_path, self_aliases=self_aliases, source=source)
    if not msgs:
        raise ValueError(_t(lang, "empty_error"))
    emit(_t(lang, "parsed", n=len(msgs)))
    parsed_path = parsed_dir / f"{safe}.json"
    # 紧凑写入：大聊天记录用 indent 会又慢又大
    with parsed_path.open("w", encoding="utf-8") as fh:
        json.dump([m.model_dump() for m in msgs], fh, ensure_ascii=False, separators=(",", ":"))
    emit(_t(lang, "parsed_written", safe=safe))

    cfg = {"model": model_config}
    emit(
        _t(lang, "calling", model=model_config.get("model", "?"), url=model_config.get("base_url", "?"))
    )
    if manual_profile:
        emit(_t(lang, "profile", profile=manual_profile))
    doc = distill(msgs, name, cfg, manual_profile=manual_profile)
    emit(_t(lang, "done"))

    persona_dir = root / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / f"{safe}.md").write_text(doc.system_prompt, encoding="utf-8")
    (persona_dir / f"{safe}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    emit(_t(lang, "persona_written", safe=safe))

    if doc.memory and not with_memory:
        emit(_t(lang, "memory_skipped", n=len(doc.memory)))
    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = write_snapshot_json(doc, str(export_dir), include_memory=with_memory)
    emit(_t(lang, "export_written", path=path))
    emit(_t(lang, "privacy"))
    return logs
