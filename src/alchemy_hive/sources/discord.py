"""Discord 聊天导出解析适配器。

支持格式：
- DiscordChatExporter 导出 JSON（含 guild/channel/messages）
- Discord 数据包（GDPR request）
"""
import json
from pathlib import Path

from ..core.models import Message


def _normalize_iso(ts: str) -> str:
    """ISO 日期 → 'YYYY-MM-DD HH:MM:SS'。"""
    import re
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", ts)
    return f"{m.group(1)} {m.group(2)}" if m else ts


class DiscordSource:
    name = "discord"
    extensions = [".json"]
    label = "Discord"

    def detect(self, path: Path) -> bool:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return False
            return "guild" in raw and "channel" in raw and "messages" in raw
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

    def parse(self, path: Path, **kwargs) -> list:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = raw.get("messages") if isinstance(raw, dict) else []
        self_aliases = {a.lower() for a in list(kwargs.get("self_aliases") or [])}
        my_id = kwargs.get("my_discord_id", "")

        out: list[Message] = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            # 跳过系统消息
            msg_type = rec.get("type", "")
            if msg_type not in ("Default", "Reply", ""):
                continue
            content = (rec.get("content") or "").strip()
            if not content:
                continue
            author = rec.get("author") or {}
            sender = author.get("name") or author.get("global_name") or "unknown"
            author_id = author.get("id", "")
            ts = _normalize_iso(rec.get("timestamp") or "")

            # 方向判断：by_author 字段或 ID 匹配
            if rec.get("by_author") is True or (my_id and author_id == my_id):
                sender = "我"
            elif sender.lower() in self_aliases or author_id in self_aliases:
                sender = "我"

            out.append(Message(sender=sender, content=content, timestamp=ts))
        return out
