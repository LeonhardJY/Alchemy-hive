"""Plugin registry：source adapter 与 exporter adapter 的自动发现与注册。

架构：PersonaDoc 是通用中间格式。Source adapter 只负责 parse → list[Message]，
Exporter adapter 只负责 PersonaDoc → 目标格式文件。注册表自动发现所有 adapter。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .models import Message, PersonaDoc


@runtime_checkable
class SourceAdapter(Protocol):
    """聊天源解析适配器：detect 判断能否处理，parse 执行解析。"""
    name: str           # 唯一标识，如 "weflow" / "telegram"
    extensions: list[str]  # 支持的文件扩展名，如 [".json"]

    def detect(self, path: Path) -> bool:
        """判断该文件是否由此 adapter 处理。"""
        ...

    def parse(self, path: Path, **kwargs) -> list[Message]:
        """解析文件为消息列表。kwargs 透传 self_aliases / source 等。"""
        ...


@runtime_checkable
class ExporterAdapter(Protocol):
    """导出适配器：PersonaDoc → 目标格式文件。"""
    name: str           # 唯一标识，如 "text" / "buzz"
    extension: str      # 输出扩展名，如 ".txt" / ".agent.json"
    label: str          # 显示名，如 "System Prompt (.txt)"

    def export(self, doc: PersonaDoc, out_dir: str, **kwargs) -> str:
        """导出并返回文件路径。"""
        ...


# ---- 全局注册表 ----

_SOURCES: dict[str, SourceAdapter] = {}
_EXPORTERS: dict[str, ExporterAdapter] = {}


def register_source(adapter: SourceAdapter) -> None:
    _SOURCES[adapter.name] = adapter


def register_exporter(adapter: ExporterAdapter) -> None:
    _EXPORTERS[adapter.name] = adapter


def get_source(name: str) -> SourceAdapter | None:
    return _SOURCES.get(name)


def get_exporter(name: str) -> ExporterAdapter | None:
    return _EXPORTERS.get(name)


def list_sources() -> dict[str, SourceAdapter]:
    return dict(_SOURCES)


def list_exporters() -> dict[str, ExporterAdapter]:
    return dict(_EXPORTERS)


def detect_source_adapter(path: Path) -> SourceAdapter | None:
    """按扩展名 + detect() 自动识别文件应由哪个 source adapter 处理。"""
    suffix = path.suffix.lower()
    candidates = [a for a in _SOURCES.values() if suffix in a.extensions]
    for adapter in candidates:
        try:
            if adapter.detect(path):
                return adapter
        except Exception:
            continue
    return None


def export_all(doc: PersonaDoc, out_dir: str, formats: list[str] | None = None, **kwargs) -> list[str]:
    """用指定格式（或全部已注册格式）导出，返回文件路径列表。"""
    exporters = _EXPORTERS
    if formats:
        exporters = {k: v for k, v in _EXPORTERS.items() if k in formats}
    paths: list[str] = []
    for name, adapter in exporters.items():
        try:
            p = adapter.export(doc, out_dir, **kwargs)
            if p:
                paths.append(p)
        except Exception:
            continue
    return paths
