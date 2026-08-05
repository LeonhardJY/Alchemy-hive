"""buzz agent 快照（buzz-agent-snapshot v1）生成与校验。"""
import json
import re
from pathlib import Path

from ..core.models import PersonaDoc
from ..core.safe import safe_filename

_FORMAT = "buzz-agent-snapshot"
_VERSION = 1

_MEMORY_LEVELS = ("none", "core", "everything")
_SLUG_RE = re.compile(r"^(core$|mem/.+)$")
_PATH_SEP_RE = re.compile(r"[/\\\\]")


def build_snapshot(doc: PersonaDoc) -> dict:
    """PersonaDoc → buzz v1 快照 dict（camelCase）。"""
    memory_entries = list(doc.memory) if doc.memory else []
    memory_level = "everything" if memory_entries else "none"
    return {
        "format": _FORMAT,
        "version": _VERSION,
        "definition": {
            "name": doc.display_name,
            "sourceIsBuiltin": False,
            "systemPrompt": doc.system_prompt,
            # model/provider 留空，导入后由用户或操作员默认决定
            "model": None,
            "provider": None,
            "runtime": None,
            "parallelism": None,
            "idleTimeoutSeconds": None,
            "maxTurnDurationSeconds": None,
        },
        "profile": {
            "displayName": doc.display_name,
            "about": doc.relationship or None,
            "avatarDataUrl": None,
            "avatarUrl": None,
        },
        "memory": {
            "level": memory_level,
            "entries": memory_entries,
        },
    }


def _expect_dict(section, field: str) -> dict:
    """快照 section 必须是 dict，否则抛 ValueError（中文提示）。"""
    if not isinstance(section, dict):
        raise ValueError(f"{field} 必须是对象（dict），收到 {type(section).__name__}")
    return section


def validate_snapshot(snapshot: dict) -> None:
    """校验 v1 快照必填约束，malformed 输入统一抛 ValueError。"""
    if not isinstance(snapshot, dict):
        raise ValueError(f"快照必须是对象（dict），收到 {type(snapshot).__name__}")
    if snapshot.get("format") != _FORMAT:
        raise ValueError(f"format 必须为 {_FORMAT}")
    if snapshot.get("version") != _VERSION:
        raise ValueError(f"version 必须为 {_VERSION}")
    definition = _expect_dict(snapshot.get("definition"), "definition")
    name = definition.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("definition.name 不能为空")
    profile = _expect_dict(snapshot.get("profile"), "profile")
    display_name = profile.get("displayName")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("profile.displayName 不能为空")
    for field, value in (("definition.name", name), ("profile.displayName", display_name)):
        if _PATH_SEP_RE.search(value):
            raise ValueError(f"{field} 不能包含路径分隔符，收到: {value!r}")
    memory = snapshot.get("memory")
    if memory is None:  # memory 缺失或显式 null → 默认空（level none、entries 空）
        memory = {}
    memory = _expect_dict(memory, "memory")
    level = memory.get("level", "none")
    if level not in _MEMORY_LEVELS:
        raise ValueError(f"memory.level 必须是 {_MEMORY_LEVELS} 之一")
    entries = memory.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("memory.entries 必须是数组（list）")
    if level == "none" and entries:
        raise ValueError("memory.level 为 none 时 entries 必须为空")
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise ValueError(f"memory.entries[{i}] 必须是对象（dict），收到 {type(e).__name__}")
        slug = str(e.get("slug") or "")
        if not _SLUG_RE.match(slug):
            raise ValueError(f"memory.entries[].slug 必须是 core 或 mem/ 前缀，收到: {slug!r}")
        body = e.get("body")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("memory.entries[].body 必须是非空字符串")


def write_snapshot_json(doc: PersonaDoc, out_path: str) -> str:
    """写 .agent.json 并返回文件路径。文件名基于用户输入的 doc.name（经安全清洗），
    display_name 只进 profile 显示、不影响文件名。"""
    snap = build_snapshot(doc)
    validate_snapshot(snap)
    safe = safe_filename(doc.name)
    p = Path(out_path) / f"{safe}.agent.json"
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)
