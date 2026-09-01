"""Instagram / Facebook（Meta）JSON 解析适配器。"""
from pathlib import Path

from ..core.parser import _parse_meta, _normalize_self, _read_head, _read_tail, _HEAD_SAMPLE


class MetaSource:
    name = "meta"
    extensions = [".json"]
    label = "Instagram / Facebook"

    def detect(self, path: Path) -> bool:
        head = _read_head(path)
        if '"timestamp_ms"' in head and '"sender_name"' in head:
            return True
        # 大文件：头部无特征时补采尾部
        if path.stat().st_size > _HEAD_SAMPLE:
            tail = _read_tail(path)
            if '"timestamp_ms"' in tail and '"sender_name"' in tail:
                return True
        return False

    def parse(self, path: Path, **kwargs) -> list:
        msgs = _parse_meta(path)
        _normalize_self(msgs, kwargs.get("self_aliases"))
        return msgs
