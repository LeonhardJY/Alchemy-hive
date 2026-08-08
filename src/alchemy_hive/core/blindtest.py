"""盲测对拍：从真实聊天抽样片段，让 agent 接话，人工评分验证蒸馏质量。"""
from .models import Message
from .distill import DistillError
from .llm import chat_completion, LLMError
from .parser import _SELF_ALIASES


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
    prompt = (
        f"{system_prompt}\n\n"
        f"下面是和你的对话上下文，请以 {name} 的口吻回复下一句，只说一句：\n\n"
        f"{_fmt_context(context_msgs)}\n"
    )
    try:
        return chat_completion(config, [{"role": "user", "content": prompt}], temperature=0.7)
    except LLMError as e:
        # 保留具体消息（如"未配置模型 API key..."），但统一转 DistillError 供调用方捕获
        raise DistillError(str(e)) from e


def rate_pairs(pairs: list[dict], ratings: dict[int, int]) -> dict:
    """汇总评分：返回条数、平均分、各条分数。"""
    scores = [ratings[i] for i in range(len(pairs)) if i in ratings]
    return {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "details": {str(i): ratings[i] for i in ratings},
    }
