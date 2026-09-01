"""WhatsApp txt 解析适配器。"""
import re
from pathlib import Path

from ..core.parser import _parse_whatsapp, _detect_encoding, _normalize_self, _read_head


class WhatsappSource:
    name = "whatsapp"
    extensions = [".txt"]
    label = "WhatsApp"

    def detect(self, path: Path) -> bool:
        head = _read_head(path)
        return bool(re.search(r"^\[\d{1,2}/\d{1,2}/\d{2,4},", head, re.M))

    def parse(self, path: Path, **kwargs) -> list:
        enc = _detect_encoding(path)
        msgs = _parse_whatsapp(path, enc)
        _normalize_self(msgs, kwargs.get("self_aliases"))
        return msgs
