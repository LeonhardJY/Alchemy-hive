"""buzz agent 快照（buzz-agent-snapshot v1）生成与校验。"""
import json
import re
from pathlib import Path

from ..core.models import PersonaDoc

_FORMAT = "buzz-agent-snapshot"
_VERSION = 1

_MEMORY_LEVELS = ("none", "core", "everything")
_SLUG_RE = re.compile(r"^(core|mem/)")


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


def validate_snapshot(snapshot: dict) -> None:
    """校验 v1 快照必填约束，不合法抛 ValueError。"""
    if snapshot.get("format") != _FORMAT:
        raise ValueError(f"format 必须为 {_FORMAT}")
    if snapshot.get("version") != _VERSION:
        raise ValueError(f"version 必须为 {_VERSION}")
    if not snapshot["definition"]["name"].strip():
        raise ValueError("definition.name 不能为空")
    if not snapshot["profile"]["displayName"].strip():
        raise ValueError("profile.displayName 不能为空")
    memory = snapshot.get("memory", {})
    level = memory.get("level", "none")
    if level not in _MEMORY_LEVELS:
        raise ValueError(f"memory.level 必须是 {_MEMORY_LEVELS} 之一")
    entries = memory.get("entries", [])
    if level == "none" and entries:
        raise ValueError("memory.level 为 none 时 entries 必须为空")
    for e in entries:
        slug = e.get("slug", "")
        if not _SLUG_RE.match(slug):
            raise ValueError(f"memory.entries[].slug 必须是 core 或 mem/ 前缀，收到: {slug!r}")
        if not str(e.get("body", "")).strip():
            raise ValueError("memory.entries[].body 不能为空")


def write_snapshot_json(doc: PersonaDoc, out_path: str) -> str:
    """写 .agent.json 并返回文件路径。文件名：{displayName}.agent.json。"""
    snap = build_snapshot(doc)
    validate_snapshot(snap)
    p = Path(out_path) / f"{doc.display_name}.agent.json"
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)
