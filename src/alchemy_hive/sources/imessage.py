"""iMessage 聊天导出解析适配器。

支持格式：
- CSV：handle,text,date,is_from_me
- TXT：2024-01-15 10:30:00 姓名: 消息内容（类似微信两行格式）

常见导出工具：imessage-exporter (Rust), ChatMate, iMazing
"""
import csv
import re
import time
from pathlib import Path

from ..core.models import Message


class ImessageSource:
    name = "imessage"
    extensions = [".csv", ".txt"]
    label = "iMessage"

    def detect(self, path: Path) -> bool:
        head = path.read_bytes()[:4096].decode("utf-8", errors="ignore")
        # CSV 格式：header 含 handle + date
        if "handle" in head.lower() and "date" in head.lower() and "is_from_me" in head.lower():
            return True
        # TXT 格式：含 is_from_me 标记
        if "is_from_me" in head.lower():
            return True
        return False

    def parse(self, path: Path, **kwargs) -> list:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return _parse_csv(path, kwargs.get("self_aliases"))
        return _parse_txt(path, kwargs.get("self_aliases"))


def _parse_csv(path: Path, self_aliases) -> list[Message]:
    """解析 iMessage CSV 导出。"""
    out: list[Message] = []
    aliases = {a.lower() for a in list(self_aliases or [])}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            handle = (row.get("handle") or "").strip()
            text = (row.get("text") or "").strip()
            is_me = row.get("is_from_me", "").strip() in ("1", "True", "true")
            date_str = (row.get("date") or "").strip()

            if not text:
                continue

            sender = "我" if is_me else (handle or "unknown")
            if not is_me and sender.lower() in aliases:
                sender = "我"

            # 尝试解析日期
            ts = _parse_date(date_str)
            out.append(Message(sender=sender, content=text, timestamp=ts))
    return out


def _parse_txt(path: Path, self_aliases) -> list[Message]:
    """解析 iMessage TXT 导出（类似微信两行格式）。"""
    out: list[Message] = []
    aliases = {a.lower() for a in list(self_aliases or [])}
    # 格式：日期 发送者: 内容 或 日期 发送者（is_from_me 标记）
    line_re = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2})\s+(.+?):\s*(.+)$")
    me_re = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2})\s+(.+?)\s*\(is_from_me\)$")

    with path.open("r", encoding="utf-8", errors="replace") as f:
        current_sender = "unknown"
        current_ts = ""
        for line in f:
            line = line.rstrip("\r\n")
            m = line_re.match(line)
            if m:
                current_ts, current_sender, content = m.groups()
                if current_sender.lower() in aliases:
                    current_sender = "我"
                out.append(Message(sender=current_sender, content=content.strip(), timestamp=current_ts))
                continue
            me_m = me_re.match(line)
            if me_m:
                current_ts, _ = me_m.groups()
                current_sender = "我"
                continue
            if line.strip() and current_sender != "unknown":
                out[-1].content += "\n" + line.strip() if out else None
    return [m for m in out if m]


def _parse_date(s: str) -> str:
    """尝试解析各种日期格式。"""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d"):
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.strptime(s[:19], fmt[:len(fmt)]))
        except (ValueError, OverflowError):
            continue
    return s
