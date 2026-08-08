"""聊天记录解析：多平台导出识别与适配。

支持微信（WeFlow JSON / 微信 txt）、Telegram JSON、WhatsApp txt、
Instagram / Facebook（Meta 数据导出，同一套 JSON 格式），以及通用字段探测兜底。
"""
import json
import re
import time
from pathlib import Path

from .models import Message

# 平台标识 → 中文名（GUI 下拉与识别结果显示共用）
SOURCE_LABELS = {
    "auto": "自动识别（推荐）",
    "weflow": "微信（WeFlow 导出）",
    "wechat": "微信 txt",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "meta": "Instagram / Facebook",
    "generic": "其他（通用字段解析）",
    "generic_json": "其他（通用 JSON）",
    "generic_txt": "其他（通用文本）",
}

# 识别采样：只读前 64KB 判断平台，避免大文件整读
_HEAD_SAMPLE = 65536

# 媒体文件名（WhatsApp/Telegram/Meta 导出里的图片/语音/文件等，解析时跳过）
_MEDIA_EXT = re.compile(
    r"\.(jpe?g|png|gif|webp|bmp|mp4|mov|opus|aac|m4a|mp3|wav|ogg|pdf|zip|rar|7z|docx?|xlsx?|ppt|apk)$",
    re.I,
)

# 发送方向探测键：WeFlow 常用 isSend=1 表示"我发的"
_DIRECTION_KEYS = ("isSend", "is_send", "sendType", "isSender")
# 字段别名：尽量认各种平台的常见命名（WeFlow/Discord/Telegram/iMessage 等）
_TEXT_KEYS = ("msgContent", "content", "text", "msg", "message", "body")
_TIME_KEYS = ("createTime", "dateTime", "time", "timestamp", "createdAt", "sentAt")
_SENDER_KEYS = ("senderUsername", "sender", "username", "nickName", "name", "author", "from", "fromUser")

_SELF_ALIASES = ("我", "self", "me")

# 通用单行 txt：'发送者: 内容'（无时间戳，适配 WhatsApp/Telegram/Discord 等拷贝文本）
_GENERIC_LINE = re.compile(r"^(?P<sender>[^:]+?):\s*(?P<content>.+)$")


# ---- 平台识别与各平台解析 ----

def _read_head(path: Path) -> str:
    """读前 _HEAD_SAMPLE 字节作为识别样本（宽容解码，识别只看特征串）。"""
    with path.open("rb") as f:
        raw = f.read(_HEAD_SAMPLE)
    return raw.decode("utf-8", errors="ignore")


def detect_source(path: str) -> str:
    """按内容特征识别导出来源平台。返回 SOURCE_LABELS 里的标识。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    head = _read_head(p)
    if p.suffix.lower() == ".json":
        if '"timestamp_ms"' in head and '"sender_name"' in head:
            return "meta"                       # Instagram / Facebook（Meta 数据导出）
        if '"isSend"' in head or '"msgContent"' in head:
            return "weflow"                     # 微信 WeFlow 导出
        if '"date"' in head and '"from"' in head and '"text"' in head:
            return "telegram"                   # Telegram Desktop 导出
        return "generic_json"
    if re.search(r"^\[\d{1,2}/\d{1,2}/\d{2,4},", head, re.M):
        return "whatsapp"                       # [MM/DD/YY, h:mm AM/PM] Sender: ...
    if re.search(r"^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}", head, re.M):
        return "wechat"                         # 微信两行格式
    return "generic_txt"


def _normalize_iso(ts: str) -> str:
    """Telegram 的 ISO 日期（'2023-07-24T09:29:09'，可能带时区）→ 'YYYY-MM-DD HH:MM:SS'。"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", ts)
    return f"{m.group(1)} {m.group(2)}" if m else ts


def _normalize_ts_ms(ms) -> str:
    """Meta 导出的 Unix 毫秒时间戳（int 或字符串）→ 本地 'YYYY-MM-DD HH:MM:SS'。"""
    try:
        if isinstance(ms, str):
            ms = float(ms)
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000))
    except Exception:
        return ""


def _telegram_text(text) -> str:
    """Telegram 的 text 可能是字符串，也可能是实体数组（['hi', {text:'bold'}]）→ 拼成纯文本。"""
    if isinstance(text, str):
        return text.strip()
    if isinstance(text, list):
        parts = [
            t if isinstance(t, str) else (t.get("text", "") if isinstance(t, dict) else "")
            for t in text
        ]
        return "".join(parts).strip()
    return ""


def _parse_telegram(path: Path) -> list[Message]:
    """Telegram Desktop 导出 JSON：messages[{type, date, from, text}]。只收文本消息。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw.get("messages") if isinstance(raw, dict) else []
    out: list[Message] = []
    for rec in records:
        if not isinstance(rec, dict) or rec.get("type") != "message":
            continue
        content = _telegram_text(rec.get("text"))
        if not content or content.startswith("[") or _MEDIA_EXT.search(content):
            continue
        sender = rec.get("from") or "unknown"
        out.append(Message(sender=str(sender), content=content, timestamp=_normalize_iso(rec.get("date") or "")))
    return out


# WhatsApp 行格式：[MM/DD/YY, h:mm(:ss) AM/PM] 发送者: 内容（内容可空 = 媒体/系统）
_WHATSAPP_LINE = re.compile(
    r"^\[(\d{1,2})/(\d{1,2})/(\d{2,4}),\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M)\]\s*"
    r"(?:(.+?):\s*(.*))?$"
)


def _wa_ts(year: int, month: int, day: int, hour: int, minute: int, second: int, ap: str) -> str:
    """WhatsApp 日期（MM/DD/YY + 12 小时制）→ 'YYYY-MM-DD HH:MM:SS'。"""
    if year < 100:
        year += 2000 if year < 50 else 1900   # '23' → 2023，'99' → 1999
    h = (hour % 12) + (12 if ap == "PM" else 0)
    return f"{year:04d}-{month:02d}-{day:02d} {h:02d}:{minute:02d}:{second:02d}"


def _parse_whatsapp(path: Path, enc: str) -> list[Message]:
    """WhatsApp 导出 txt：[日期, 时间 AM/PM] 发送者: 内容。跳过媒体/系统行，续行接上一句。"""
    out: list[Message] = []
    with path.open("r", encoding=enc) as f:
        for line in f:
            line = line.rstrip("\r\n")
            m = _WHATSAPP_LINE.match(line)
            if m:
                mo, da, yr, hh, mm, ss, ap, sender, content = m.groups()
                sender = (sender or "").strip()
                content = (content or "").strip()
                if not sender or not content or content.startswith("[") or _MEDIA_EXT.search(content):
                    continue
                out.append(Message(
                    sender=sender,
                    content=content,
                    timestamp=_wa_ts(int(yr), int(mo), int(da), int(hh), int(mm), int(ss or 0), ap),
                ))
            elif out and line.strip() and not line.strip().startswith("["):
                # 续行：长消息换行，接在上一句末尾
                out[-1].content += "\n" + line.strip()
    return out


def _parse_meta(path: Path) -> list[Message]:
    """Instagram / Facebook 数据导出（同一套 Meta JSON）：messages[{sender_name, content, timestamp_ms}]。

    文件里消息是新的在前，解析后按时间升序排（蒸馏的『近期』要取末尾）。
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw.get("messages") if isinstance(raw, dict) else []
    out: list[Message] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        content = (rec.get("content") or "").strip()
        if not content or content.startswith("[") or _MEDIA_EXT.search(content):
            continue
        sender = rec.get("sender_name") or "unknown"
        out.append(Message(
            sender=str(sender),
            content=content,
            timestamp=_normalize_ts_ms(rec.get("timestamp_ms")),
        ))
    out.sort(key=lambda m: m.timestamp or "0000-00-00 00:00:00")
    return out


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
    """流式逐行解析（不整读/不 splitlines 复制），峰值内存只与消息数相关，与文件大小解耦。

    优先微信两行格式（时间戳 + 内容）；整份文件无时间戳时退回「发送者: 内容」单行格式。
    """
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
        # 不是微信两行格式：尝试通用单行格式（其他平台拷贝的文本）
        generic = _parse_generic_txt(path, enc)
        if generic:
            return generic
        raise ValueError(
            f"未识别为微信导出的 txt：整份文件没有『时间戳 发送者』格式的行，请检查导出格式"
        )
    return out


def _parse_generic_txt(path: Path, enc: str) -> list[Message]:
    """通用单行格式：每行 '发送者: 内容'。无时间戳，timestamp 留空。"""
    out: list[Message] = []
    with path.open("r", encoding=enc) as f:
        for line in f:
            line = line.rstrip("\r\n").strip()
            if not line:
                continue
            m = _GENERIC_LINE.match(line)
            if not m:
                continue
            sender = m.group("sender").strip()
            content = m.group("content").strip()
            if sender and content and not content.startswith("["):
                out.append(Message(sender=sender, content=content, timestamp=""))
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


def _normalize_self(messages: list[Message], self_aliases: list[str] | None = None) -> None:
    """把『你』的消息发送者统一归一化为『我』，供下游（盲测对拍等）区分方向。

    默认认 me/self/我；其他平台导出没有方向标记时，用 --self 传入你的昵称。
    """
    aliases = {
        a.strip().lower()
        for a in list(_SELF_ALIASES) + list(self_aliases or [])
        if a and a.strip()
    }
    for m in messages:
        if m.sender.strip().lower() in aliases:
            m.sender = "我"


def _dispatch(fmt: str, p: Path) -> list[Message]:
    """按识别结果解析；generic/wechat/weflow 等落在通用探字段解析上。"""
    if fmt in ("weflow", "generic_json") or (fmt == "generic" and p.suffix.lower() == ".json"):
        return _parse_json(p)
    if fmt == "telegram":
        return _parse_telegram(p)
    if fmt == "meta":
        return _parse_meta(p)
    if fmt == "whatsapp":
        return _parse_whatsapp(p, _detect_encoding(p))
    if fmt in ("wechat", "generic_txt") or (fmt == "generic" and p.suffix.lower() == ".txt"):
        return _parse_txt(p)
    raise ValueError(f"未知来源: {fmt}")


def parse_messages(path: str, self_aliases: list[str] | None = None, source: str | None = None) -> list[Message]:
    """解析聊天文件。source 可选：'auto' / 平台标识；缺省自动识别。

    self_aliases：你的昵称列表（配合 --self），把你自己归一化为『我』。
    显式指定 source 解析失败时，宽松回退到自动识别。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    suffix = p.suffix.lower()
    if suffix not in (".json", ".txt"):
        raise ValueError(f"不支持的文件类型: {suffix}（支持 .json / .txt）")
    if source and source != "auto":
        # 平台与扩展名不符（如对 JSON 强选 WhatsApp）→ 直接按自动识别，避免产出垃圾
        json_fmt = source in ("weflow", "telegram", "meta", "generic_json")
        txt_fmt = source in ("wechat", "whatsapp", "generic_txt")
        if (json_fmt and suffix != ".json") or (txt_fmt and suffix != ".txt"):
            source = None
        else:
            try:
                msgs = _dispatch(source, p)
                if not msgs:
                    msgs = _dispatch(detect_source(str(p)), p)  # 显式指定解析不出 → 回退自动识别
                else:
                    _normalize_self(msgs, self_aliases)
                    return msgs
            except Exception:
                pass  # 用户选错平台 → 回退自动识别
    msgs = _dispatch(detect_source(str(p)), p)
    _normalize_self(msgs, self_aliases)
    return msgs
