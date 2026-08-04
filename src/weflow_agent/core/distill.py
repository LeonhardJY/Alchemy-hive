"""蒸馏引擎：LLM（OpenAI-compatible）优先，无 key 时规则兜底。"""
import json
import re
from collections import Counter

import httpx

from .models import Message, PersonaDoc
from .prompt import DISTILL_PROMPT

_SELF_ALIASES = ("我", "self", "me")
_HARD_RULES = [
    "一次只说一句话，发完等对方回复；可以连发但每条都是碎片",
    "单条消息尽量短，多用单字和短语（走/6/蛤/是了/卧槽）",
    "禁止书面语和完整长句，禁止比喻、排比、总结、抒情",
    "口语语气直接丢出来（蛤/嗷/emmm），不需要每句都有标点",
]


def load_config(path: str | None) -> dict:
    """读 toml 配置；无文件返回空 dict。支持 .weflow-agent/config.toml。"""
    if not path:
        return {}
    from pathlib import Path
    try:
        import tomllib  # py3.11+
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
    """调 OpenAI-compatible 接口蒸馏；失败返回 None（由调用方兜底）。"""
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
        return PersonaDoc(name=name, display_name=name, **{k: v for k, v in payload.items() if k in PersonaDoc.model_fields})
    except Exception:
        return None


def _rule_fallback(messages: list[Message], name: str) -> PersonaDoc:
    """无 LLM 时规则兜底：统计对方高频词，生成基础 prompt。"""
    theirs = [m.content for m in messages if m.sender not in _SELF_ALIASES]
    words = [w for t in theirs for w in re.findall(r"[一-鿿]{1,4}", t)]
    top = [w for w, _ in Counter(words).most_common(8) if len(w) >= 2][:6]
    examples = [t[:40] for t in theirs if 2 <= len(t) <= 20][:5]
    prompt_lines = [
        f"你是{name}，以下是聊天记录提炼出的人物提示词。",
        "",
        "# 表达硬规则（必须遵守）",
        *[f"- {r}" for r in _HARD_RULES],
        "",
        "# 高频词",
        *[f"- {w}" for w in top],
        "",
        "# 参考例句（摘自聊天记录）",
        *[f"- {e}" for e in examples],
    ]
    return PersonaDoc(
        name=name,
        display_name=name,
        expression_rules=_HARD_RULES,
        signature_phrases=top,
        system_prompt="\n".join(prompt_lines),
    )


def distill(messages: list[Message], name: str, config: dict) -> PersonaDoc:
    """入口：LLM 蒸馏，失败或无 key 时规则兜底。"""
    doc = _llm_distill(messages, name, config)
    if doc is not None and doc.system_prompt:
        return doc
    return _rule_fallback(messages, name)
