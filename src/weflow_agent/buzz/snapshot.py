"""buzz agent 快照（buzz-agent-snapshot v1）生成与校验。"""
import json
from pathlib import Path

from ..core.models import PersonaDoc

_FORMAT = "buzz-agent-snapshot"
_VERSION = 1


def build_snapshot(doc: PersonaDoc) -> dict:
    """PersonaDoc → buzz v1 快照 dict（camelCase）。"""
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
            "level": "none",
            "entries": [],
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


def write_snapshot_json(doc: PersonaDoc, out_path: str) -> str:
    """写 .agent.json 并返回文件路径。文件名：{displayName}.agent.json。"""
    snap = build_snapshot(doc)
    validate_snapshot(snap)
    p = Path(out_path) / f"{doc.display_name}.agent.json"
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)
