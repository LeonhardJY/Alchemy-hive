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


# 微信 txt 行格式：时间戳 + 分隔符(含   等特殊空白) + 发送者(可带引号，也可不带)
_TIME_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2})\s*['\"]?(.+?)['\"]?\s*$")

# 编码探测：只读前 256KB 判断，避免大文件反复整读
_ENCODINGS = ("utf-8-sig", "utf-8", "gbk")
_ENCODING_SAMPLE = 262144


def _detect_encoding(path: Path) -> str:
    with path.open("rb") as f:
        head = f.read(_ENCODING_SAMPLE)
    for enc in _ENCODINGS:
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别的文件编码: {path}（尝试 utf-8/gbk 均失败）")


def _parse_txt_with_encoding(path: Path, enc: str) -> list[Message]:
    """流式逐行解析（不整读/不 splitlines 复制），峰值内存只与消息数相关，与文件大小解耦。"""
    out: list[Message] = []
    current_sender = "unknown"
    current_ts = ""
    saw_timestamp = False
    with path.open("r", encoding=enc) as f:
        for line in f:
            line = line.rstrip("\r\n")
            m = _TIME_LINE.match(line)
            if m:
                saw_timestamp = True
                current_ts, current_sender = m.groups()
                continue
            if line.strip() and not line.startswith("["):
                out.append(Message(sender=current_sender, content=line.strip(), timestamp=current_ts))
    if out and not saw_timestamp:
        raise ValueError(
            f"未识别为微信导出的 txt：整份文件没有『时间戳 发送者』格式的行，请检查导出格式"
        )
    return out


def _parse_txt(path: Path) -> list[Message]:
    """解析 txt：采样判编码 → 流式读；若中途解码失败（采样误判等）回退 gbk。"""
    enc = _detect_encoding(path)
    try:
        return _parse_txt_with_encoding(path, enc)
    except UnicodeDecodeError:
        # 罕见：ASCII 开头 + 后面才出现中文，采样判成 utf-8 但 gbk 文件 → 改 gbk 重试
        try:
            return _parse_txt_with_encoding(path, "gbk")
        except UnicodeDecodeError:
            raise ValueError(f"文件 {path} 解码失败：包含非法字符，可能已损坏")


def parse_messages(path: str) -> list[Message]:
    """按扩展名解析聊天文件。.json → WeFlow；.txt → 微信导出。

    合法空 JSON（{messages: []}）与空 txt 返回空列表；使用方（distill/import）自行处理空态。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.suffix.lower() == ".json":
        return _parse_json(p)
    if p.suffix.lower() == ".txt":
        return _parse_txt(p)
    raise ValueError(f"不支持的文件类型: {p.suffix}（支持 .json / .txt）")
