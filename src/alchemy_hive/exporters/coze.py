"""Coze Bot Config JSON 导出。

Coze 是字节跳动推出的 AI Bot 构建平台，使用简单 JSON 配置定义 Bot。
导出 PersonaDoc 为 Coze 兼容的 bot config JSON。
"""
import json
from pathlib import Path

from ..core.safe import safe_filename


class CozeExporter:
    """导出 PersonaDoc 为 Coze Bot Config JSON 格式（.json）。"""
    name = "coze"
    extension = ".json"
    label = "Coze Bot Config (.json)"

    def export(self, doc, out_dir: str, **kwargs) -> str:
        system_prompt = doc.system_prompt or ""

        # 构建 Coze 兼容的 bot config
        config = {
            "name": doc.display_name or doc.name,
            "description": _build_description(doc),
            "personality": _build_personality(doc),
            "first_message": _build_first_message(doc),
            "system_prompt": system_prompt,
        }

        safe = safe_filename(doc.name)
        p = Path(out_dir) / f"{safe}.coze.json"
        p.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)


def _build_description(doc) -> str:
    """从 PersonaDoc 构建 bot 描述。"""
    parts = []
    if doc.relationship:
        parts.append(f"关系：{doc.relationship}")
    if doc.relationship_context:
        parts.append(doc.relationship_context)
    if doc.expression_rules:
        parts.append("表达规则：" + "；".join(doc.expression_rules[:5]))
    if doc.signature_phrases:
        parts.append("口头禅：" + "、".join(doc.signature_phrases[:5]))
    return "\n".join(parts) or f"{doc.display_name or doc.name} 的角色描述。"


def _build_personality(doc) -> str:
    """从 PersonaDoc 构建性格描述。"""
    parts = []
    if doc.profile:
        tags = doc.profile.get("tags", [])
        if tags:
            parts.append("性格关键词：" + "、".join(tags[:8]))
    if doc.rhythm:
        parts.append("说话节奏：" + doc.rhythm)
    return "；".join(parts) or "自然、真实。"


def _build_first_message(doc) -> str:
    """从 PersonaDoc 的 example_replies 构建开场白。"""
    if doc.example_replies:
        for scene, replies in doc.example_replies.items():
            if isinstance(replies, list) and replies:
                return replies[0]
    return f"嗨，我是{doc.display_name or doc.name}。"
