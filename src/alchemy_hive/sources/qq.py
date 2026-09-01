"""QQ 消息导出解析适配器。

支持格式：各种 QQ 导出工具的 JSON 格式。
常见工具：LiteLoaderQQNT 插件、QQ 数据包导出、NTQQ 导出等。
"""
import json
import time
from pathlib import Path

from ..core.models import Message


class QQSource:
    name = "qq"
    extensions = [".json"]
    label = "QQ"

    def detect(self, path: Path) -> bool:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or not raw:
                return False
            first = raw[0]
            if not isinstance(first, dict):
                return False
            # QQ 消息特征：sender 含 user_id/nickname + time 字段
            sender = first.get("sender") or {}
            has_sender = isinstance(sender, dict) and ("user_id" in sender or "nickname" in sender)
            has_time = "time" in first
            has_content = "content" in first or "message" in first
            return has_sender and has_time and has_content
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

    def parse(self, path: Path, **kwargs) -> list:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        self_aliases = {a.lower() for a in list(kwargs.get("self_aliases") or [])}
        my_qq = kwargs.get("my_qq_id", "")

        out: list[Message] = []
        for rec in raw:
            if not isinstance(rec, dict):
                continue
            sender_info = rec.get("sender") or {}
            if not isinstance(sender_info, dict):
                continue

            # 提取内容：支持 content.text 和 message 字段
            content = ""
            content_field = rec.get("content")
            if isinstance(content_field, dict):
                content = content_field.get("text", "")
            elif isinstance(content_field, str):
                content = content_field
            if not content:
                msg_field = rec.get("message")
                if isinstance(msg_field, str):
                    content = msg_field
                elif isinstance(msg_field, list):
                    parts = []
                    for item in msg_field:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            parts.append(item)
                    content = "".join(parts)
            content = content.strip()
            if not content:
                continue

            sender_name = sender_info.get("nickname") or sender_info.get("card") or "unknown"
            sender_id = str(sender_info.get("user_id", ""))

            # 时间戳：Unix 秒
            ts_raw = rec.get("time", 0)
            try:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(ts_raw)))
            except (ValueError, OverflowError, TypeError):
                ts = ""

            # 方向判断
            if sender_name.lower() in self_aliases or (my_qq and sender_id == my_qq):
                sender_name = "我"

            out.append(Message(sender=sender_name, content=content, timestamp=ts))
        return out
