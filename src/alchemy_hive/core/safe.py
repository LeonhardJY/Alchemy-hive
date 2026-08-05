"""安全文件名工具：防止用户输入导致的路径穿越。"""
import re

# Windows 保留设备名（不区分大小写）：con/prn/aux/nul + com1-9 + lpt1-9
_RESERVED = (
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_INVALID_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(name: str) -> str:
    """把任意字符串转成安全的单层文件名：去除路径分隔符/非法字符、空名/./.. 兜底、去尾点空格。"""
    s = _INVALID_RE.sub("_", (name or "").strip())
    if not s or s in (".", ".."):
        s = "unnamed"
    s = s.rstrip(". ")
    if s.lower() in _RESERVED:
        s = "_" + s
    return s or "unnamed"
