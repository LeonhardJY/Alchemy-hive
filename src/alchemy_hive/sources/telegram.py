"""Telegram Desktop JSON 解析适配器。"""
from pathlib import Path

from ..core.parser import _parse_telegram, _normalize_self, _read_head


class TelegramSource:
    name = "telegram"
    extensions = [".json"]
    label = "Telegram"

    def detect(self, path: Path) -> bool:
        head = _read_head(path)
        return '"date"' in head and '"from"' in head and '"text"' in head

    def parse(self, path: Path, **kwargs) -> list:
        msgs = _parse_telegram(path)
        _normalize_self(msgs, kwargs.get("self_aliases"))
        return msgs
