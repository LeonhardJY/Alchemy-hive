"""WeChat txt 解析适配器。"""
import re
from pathlib import Path

from ..core.parser import _parse_txt, _normalize_self, _read_head


class WechatSource:
    name = "wechat"
    extensions = [".txt"]
    label = "微信 txt"

    def detect(self, path: Path) -> bool:
        head = _read_head(path)
        return bool(re.search(r"^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}", head, re.M))

    def parse(self, path: Path, **kwargs) -> list:
        msgs = _parse_txt(path)
        _normalize_self(msgs, kwargs.get("self_aliases"))
        return msgs
