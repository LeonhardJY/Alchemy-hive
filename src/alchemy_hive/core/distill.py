"""蒸馏引擎：LLM（OpenAI-compatible）蒸馏，无 key 或失败时抛 DistillError。"""
import json
import re

import httpx

from .models import Message, PersonaDoc
from .prompt import DISTILL_PROMPT


class DistillError(RuntimeError):
    """蒸馏失败：缺少模型配置或 LLM 调用失败。"""


def load_config(path: str | None) -> dict:
    """读 toml 配置；无文件返回空 dict。支持 .alchemy-hive/config.toml。"""
    if not path:
        return {}
    from pathlib import Path
    try:
        import tomllib  # py3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # py3.10 兼容
        except ModuleNotFoundError:
            return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _sample_text(messages: list[Message], limit: int = 200) -> str:
    return "\n".join(f"{m.timestamp} {m.sender}: {m.content[:80]}" for m in messages[:limit])


def _llm_distill(messages: list[Message], name: str, config: dict) -> PersonaDoc | None:
    """调 OpenAI-compatible 接口蒸馏；失败返回 None（由 distill 抛 DistillError）。"""
    model = (config.get("model") or {}).get("base_url"), (config.get("model") or {}).get("api_key"), (config.get("model") or {}).get("model")
    base_url, api_key, model_name = model
    if not api_key:
        return None
    prompt = DISTILL_PROMPT.replace("{name}", name).replace("{chat_sample}", _sample_text(messages))
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        payload = json.loads(re.sub(r"```(json)?|```", "", content).strip())
        data = dict(payload)
        data["name"] = name                      # 强制参数名
        data.setdefault("display_name", name)    # 有则用模型的，无则用参数
        clean = {k: v for k, v in data.items() if k in PersonaDoc.model_fields}
        doc = PersonaDoc(**clean)
        # C2: 把 LLM 结构化字段渲染成 system_prompt，避免 distill() 守卫判空走兜底
        rules = data.get("expression_rules") or doc.expression_rules or []
        phrases = data.get("signature_phrases") or doc.signature_phrases or []
        repls = data.get("example_replies") or doc.example_replies or {}
        memories = data.get("memory") or doc.memory or []
        relationship = data.get("relationship") or doc.relationship or ""
        prompt_lines = [
            f"你是{doc.display_name}。{relationship}".rstrip("。") + "。",
            "",
            "# 表达硬规则（必须遵守）",
            *[f"- {r}" for r in rules],
            "",
            "# 高频口头禅/语气词",
            *[f"- {w}" for w in phrases],
            "",
            "# 场景例句（摘自聊天记录）",
        ]
        for scene, lines in repls.items():
            prompt_lines.append(f"## {scene}")
            for line in (lines if isinstance(lines, list) else [lines]):
                prompt_lines.append(f"- {line}")
        if memories:
            prompt_lines.append("")
            prompt_lines.append("# 共同回忆")
            for m in memories:
                if isinstance(m, dict):
                    prompt_lines.append(f"- {m.get('body', str(m))}")
        doc.system_prompt = "\n".join(prompt_lines)
        return doc
    except Exception:
        return None


def distill(messages: list[Message], name: str, config: dict) -> PersonaDoc:
    """入口：LLM 蒸馏。无 api_key 或调用失败时抛 DistillError，绝不兜底。"""
    api_key = (config.get("model") or {}).get("api_key")
    if not api_key:
        raise DistillError(
            "未配置模型 API key。请配置 .alchemy-hive/config.toml 的 [model] api_key，"
            "或使用 `alchemy-hive gui` 在界面中填写。"
        )
    doc = _llm_distill(messages, name, config)
    if doc is None or not doc.system_prompt:
        raise DistillError("LLM 蒸馏失败，请检查 base_url/api_key/model 配置与网络连接。")
    return doc
