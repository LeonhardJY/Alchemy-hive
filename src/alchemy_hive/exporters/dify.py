"""Dify App DSL YAML 导出。

Dify 是开源的 LLM 应用开发平台，使用 DSL YAML 格式定义 App 配置。
导出 PersonaDoc 为 Dify 兼容的 chat-mode app config。
"""
import json
from pathlib import Path

import yaml

from ..core.safe import safe_filename


class DifyExporter:
    """导出 PersonaDoc 为 Dify App DSL YAML 格式（.yml）。"""
    name = "dify"
    extension = ".yml"
    label = "Dify App DSL (.yml)"

    def export(self, doc, out_dir: str, **kwargs) -> str:
        system_prompt = doc.system_prompt or ""

        # 构建 Dify 兼容的 DSL YAML
        config = {
            "app": {
                "name": doc.display_name or doc.name,
                "description": _build_description(doc),
                "mode": "chat",
            },
            "model_config": {
                "prompt_template": [
                    {
                        "text": system_prompt,
                        "role": "system",
                    }
                ],
            },
        }

        safe = safe_filename(doc.name)
        p = Path(out_dir) / f"{safe}.dify.yml"
        p.write_text(yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
        return str(p)


def _build_description(doc) -> str:
    """从 PersonaDoc 构建 app 描述。"""
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
