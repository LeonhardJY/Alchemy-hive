"""通用 JSON/txt 解析适配器（兜底）。"""
import re
from pathlib import Path

from ..core.parser import (
    _parse_json, _parse_txt, _normalize_self, _read_head,
    _HEAD_SAMPLE, _MEDIA_EXT,
)


class GenericSource:
    name = "generic"
    extensions = [".json", ".txt"]
    label = "其他（通用字段解析）"

    def detect(self, path: Path) -> bool:
        """通用适配器：总是返回 True（作为兜底）。"""
        return True

    def parse(self, path: Path, **kwargs) -> list:
        suffix = path.suffix.lower()
        if suffix == ".json":
            msgs = _parse_json(path)
        else:
            msgs = _parse_txt(path)
        _normalize_self(msgs, kwargs.get("self_aliases"))
        return msgs
