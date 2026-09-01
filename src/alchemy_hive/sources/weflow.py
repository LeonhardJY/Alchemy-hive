"""WeChat WeFlow JSON 解析适配器。"""
from pathlib import Path

from ..core.parser import _parse_json, _normalize_self, _read_head, _HEAD_SAMPLE


class WeflowSource:
    name = "weflow"
    extensions = [".json"]
    label = "微信（WeFlow 导出）"

    def detect(self, path: Path) -> bool:
        head = _read_head(path)
        return '"isSend"' in head or '"msgContent"' in head

    def parse(self, path: Path, **kwargs) -> list:
        msgs = _parse_json(path)
        _normalize_self(msgs, kwargs.get("self_aliases"))
        return msgs
