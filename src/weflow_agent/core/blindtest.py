"""盲测对拍：从真实聊天抽样片段，让 agent 接话，人工评分验证蒸馏质量。"""
import json
import re

import httpx

from .models import Message
from .distill import load_config, DistillError

_SELF_ALIASES = ("我", "self", "me")


def extract_pairs(messages: list[Message], n: int, context_len: int = 3) -> list[dict]:
    """抽取 n 个对话对：context 为上文（对方+自己），real_reply 为对方最后发言。"""
    pairs: list[dict] = []
    for i, m in enumerate(messages):
        if m.sender in _SELF_ALIASES:
            continue
        if len(pairs) >= n:
            break
        ctx = messages[max(0, i - context_len):i]
        if ctx:
            pairs.append({"context": ctx, "real_reply": m})
    return pairs


def _fmt_context(context: list[Message]) -> str:
    return "\n".join(f"{m.sender}: {m.content}" for m in context)


def ask_agent(context_msgs: list[Message], name: str, system_prompt: str, config: dict) -> str:
    """用蒸馏出的 persona + 模型，让 agent 以 {name} 的口吻接话。"""
    model = config.get("model") or {}
    missing = [k for k in ("base_url", "api_key", "model") if not model.get(k)]
    if missing:
        labels = "、".join({"base_url": "base_url", "api_key": "API key", "model": "model"}[k] for k in missing)
        raise DistillError(f"未配置模型 {labels}，请先配置 [model] 段相应字段。")
    prompt = (
        f"{system_prompt}\n\n"
        f"下面是和你的对话上下文，请以 {name} 的口吻回复下一句，只说一句：\n\n"
        f"{_fmt_context(context_msgs)}\n"
    )
    try:
        resp = httpx.post(
            f"{model['base_url'].rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {model['api_key']}"},
            json={"model": model["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPError as e:
        # ConnectError / TimeoutException / HTTPStatusError 等网络与 HTTP 异常
        raise DistillError("LLM 调用失败，请检查配置和网络") from e
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        # 响应 JSON 解析失败或结构不符（JSONDecodeError 是 ValueError 子类，一并覆盖）
        raise DistillError("LLM 调用失败，请检查配置和网络") from e


def rate_pairs(pairs: list[dict], agent_replies: list[str], ratings: dict[int, int]) -> dict:
    """汇总评分：返回条数、平均分、各条分数。"""
    scores = [ratings[i] for i in range(len(pairs)) if i in ratings]
    return {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "details": {str(i): ratings[i] for i in ratings},
    }
