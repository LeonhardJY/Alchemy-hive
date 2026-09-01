"""Slack 频道导出解析适配器。

支持格式：Slack workspace export 解压后的频道 JSON 文件。
用户导出后解压，每个频道一个 JSON 文件（如 general.json）。
用户名映射需要 users.json（同级目录），但也可从 message 的 user_id 直接用。
"""
import json
import time
from pathlib import Path

from ..core.models import Message


class SlackSource:
    name = "slack"
    extensions = [".json"]
    label = "Slack"

    def detect(self, path: Path) -> bool:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or not raw:
                return False
            first = raw[0]
            if not isinstance(first, dict):
                return False
            # Slack 消息特征：type + ts + text，无 sender_name（与 Meta 区分）
            return ("type" in first and "ts" in first and "text" in first
                    and "sender_name" not in first)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

    def parse(self, path: Path, **kwargs) -> list:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []

        # 尝试加载同级 users.json 做用户名映射
        user_map = _load_users_map(path)

        self_aliases = {a.lower() for a in list(kwargs.get("self_aliases") or [])}
        out: list[Message] = []
        for rec in raw:
            if not isinstance(rec, dict):
                continue
            if rec.get("type") != "message":
                continue
            content = (rec.get("text") or "").strip()
            if not content or content.startswith("<"):
                continue  # 跳过系统消息和 Slack 特殊格式（如 <@U123>）

            # 用户名：优先从 users.json 映射，否则用 user_id
            user_id = rec.get("user") or ""
            sender = user_map.get(user_id, user_id) or "unknown"

            ts_raw = rec.get("ts") or "0"
            try:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(float(ts_raw)))
            except (ValueError, OverflowError):
                ts = ""

            # 方向判断
            if sender.lower() in self_aliases or user_id in self_aliases:
                sender = "我"

            out.append(Message(sender=sender, content=content, timestamp=ts))
        return out


def _load_users_map(channel_path: Path) -> dict[str, str]:
    """从同级目录的 users.json 加载 user_id → display_name 映射。"""
    users_path = channel_path.parent / "users.json"
    if not users_path.exists():
        return {}
    try:
        users = json.loads(users_path.read_text(encoding="utf-8"))
        if not isinstance(users, list):
            return {}
        return {u.get("id", ""): u.get("name") or u.get("real_name") or u.get("id", "")
                for u in users if isinstance(u, dict)}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
