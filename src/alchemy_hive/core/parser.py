"""聊天记录解析：支持 WeFlow 导出 JSON 与微信导出 txt。宽容探测字段名。"""
import json
import re
from pathlib import Path

from .models import Message

# 发送方向探测键：WeFlow 常用 isSend=1 表示"我发的"
_DIRECTION_KEYS = ("isSend", "is_send", "sendType", "isSender")
_TEXT_KEYS = ("msgContent", "content", "text", "msg")
_TIME_KEYS = ("createTime", "dateTime", "time", "timestamp")
_SENDER_KEYS = ("senderUsername", "sender", "username", "nickName", "name")

_SELF_ALIASES = ("我", "self", "me")


def infer_direction(msg_sender: str, self_aliases: list[str] | None = None) -> str:
    """判断发送方向。返回 "me"（本人）或 "them"（对方）。"""
    if self_aliases is None:
        self_aliases = list(_SELF_ALIASES)
    if msg_sender.lower() in (a.lower() for a in self_aliases):
        return "me"
    return "them"


def _probe(record: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        if k in record and record[k] is not None:
            return str(record[k])
    return ""


def _parse_json(path: Path) -> list[Message]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        if "messages" not in raw and "data" not in raw:
            raise ValueError(
                "无法识别的 WeFlow JSON 结构：期望顶层数组或 {messages:[...]} 或 {data:[...]}"
            )
        records = raw.get("messages", raw.get("data"))
    else:
        raise ValueError(
            "无法识别的 WeFlow JSON 结构：期望顶层数组或 {messages:[...]} 或 {data:[...]}"
        )
    if not isinstance(records, list):
        raise ValueError(
            "无法识别的 WeFlow JSON 结构：期望顶层数组或 {messages:[...]} 或 {data:[...]}"
        )
    out: list[Message] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        content = _probe(rec, _TEXT_KEYS)
        if not content or content.startswith("["):  # 跳过图片/表情/链接等占位
            continue
        sender = _probe(rec, _SENDER_KEYS) or "unknown"
        # 方向探测：遍历所有方向键取原始值（保留 bool/int/float/str 类型）。
        # 值为真 → 本人；值为假但 sender 是本人别名（me/self/我，忽略大小写/空白）→ 也归一化为"我"，
        # 避免下游 extract_pairs 只认精确值导致本人被误判对方。
        if any(k in rec for k in _DIRECTION_KEYS):
            dir_val = None
            for k in _DIRECTION_KEYS:
                if k in rec and rec[k] is not None:
                    dir_val = rec[k]
                    break
            if dir_val is not None:
                truthy = False
                if isinstance(dir_val, bool):
                    truthy = dir_val
                elif isinstance(dir_val, (int, float)):
                    truthy = bool(dir_val)
                elif isinstance(dir_val, str):
                    if dir_val.lower() in ("1", "true", "send", "yes"):
                        truthy = True
                    elif infer_direction(dir_val) == "me":
                        truthy = True
                if truthy:
                    sender = "我"
                elif infer_direction(sender.strip()) == "me":
                    sender = "我"
        ts = _probe(rec, _TIME_KEYS)
        out.append(Message(sender=sender, content=content, timestamp=ts))
    return out


_TIME_LINE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) '(.+?)'\s*$")


def _parse_txt(path: Path) -> list[Message]:
    text = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"无法解码文件: {path}（尝试 utf-8/gbk 均失败）")
    out: list[Message] = []
    current_sender = "unknown"
    current_ts = ""
    for line in text.splitlines():
        m = _TIME_LINE.match(line)
        if m:
            current_ts, current_sender = m.groups()
            continue
        if line.strip() and not line.startswith("["):
            out.append(Message(sender=current_sender, content=line.strip(), timestamp=current_ts))
    return out


def parse_messages(path: str) -> list[Message]:
    """按扩展名解析聊天文件。.json → WeFlow；.txt → 微信导出。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.suffix.lower() == ".json":
        return _parse_json(p)
    if p.suffix.lower() == ".txt":
        return _parse_txt(p)
    raise ValueError(f"不支持的文件类型: {p.suffix}（支持 .json / .txt）")
