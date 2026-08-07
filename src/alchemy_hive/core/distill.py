"""蒸馏引擎（核心）：两阶段 LLM 蒸馏，对齐 dot-skill。

Stage 1 analyze：跨时间线抽样聊天 → LLM 输出结构化分析 JSON（性格/表达/情绪逻辑/10-30 条带原话的记忆）。
Stage 2 build：基于分析 JSON → LLM 写出 ≥400 行的完整角色 persona（Markdown），作为最终 system_prompt。
build 失败时降级为结构化渲染（build_system_prompt），绝不返回空。
"""
import json
import re

from .models import Message, PersonaDoc
from .prompt import ANALYZE_PROMPT, BUILD_PROMPT, build_system_prompt
from .llm import chat_completion, LLMError


class DistillError(LLMError):
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


# 样本策略（对齐 dot-skill：近期完整正文 + 早期抽样，不截断正文）
_SAMPLE_RECENT = 1500   # 近期完整消息数（覆盖当前关系动态）
_SAMPLE_EARLY = 300     # 早期消息数（覆盖共同记忆来源）
_PER_MSG_CAP = 1000     # 单条超长消息兜底截断（罕见），正文默认完整


def _sample_text(messages: list[Message], recent: int = _SAMPLE_RECENT, early: int = _SAMPLE_EARLY, per_msg_cap: int = _PER_MSG_CAP) -> str:
    """近期完整 + 早期抽样；正文不截断（仅单条超长时兜底截断）。"""
    if len(messages) <= recent:
        picked = list(messages)
    else:
        picked = messages[:early] + messages[-recent:]
    parts = []
    for m in picked:
        content = m.content or ""
        if per_msg_cap and len(content) > per_msg_cap:
            content = content[:per_msg_cap] + "…"
        parts.append(f"{m.timestamp} {m.sender}: {content}")
    return "\n".join(parts)


def _parse_json_object(content: str) -> dict | None:
    try:
        payload = json.loads(re.sub(r"```(json)?|```", "", content).strip())
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _chat(config: dict, messages: list[dict], *, temperature: float, json_mode: bool = False, max_tokens: int | None = None, timeout: float = 180) -> str:
    """带 max_tokens 上限的 LLM 调用：供应商拒绝 max_tokens（400）时去掉再试；
    网络类错误（超时/无法连接）立即抛出让上层暴露，不做无意义重试。失败抛 LLMError。"""
    attempts = [{"max_tokens": max_tokens}, {}] if max_tokens else [{}]
    last_error: LLMError | None = None
    for kwargs in attempts:
        try:
            return chat_completion(config, messages, temperature=temperature, json_mode=json_mode, max_retries=1, timeout=timeout, **kwargs)
        except LLMError as e:
            if "超时" in str(e) or "无法连接" in str(e):
                raise
            last_error = e
            continue
    raise last_error if last_error else LLMError("LLM 调用失败")


def _build_config(config: dict) -> dict:
    """build 阶段模型覆盖：配置里有 [build] 段（base_url/api_key/model）则用它撰写，否则用 [model]。"""
    build = config.get("build") or {}
    if build.get("base_url") and build.get("api_key") and build.get("model"):
        return {"model": build}
    return config


def _analyze_pass(messages: list[Message], name: str, config: dict, manual_profile: str = "", fix: str = "") -> dict:
    """Stage 1：结构化分析。成功返回分析 dict；任何失败抛 DistillError 并暴露原始响应，便于诊断。"""
    sample = _sample_text(messages)
    prompt = (
        ANALYZE_PROMPT
        .replace("{name}", name)
        .replace("{manual_profile}", manual_profile or "（用户未提供，完全依据聊天记录）")
        .replace("{fix}", fix or "（无）")
        .replace("{count}", str(len(messages)))
        .replace("{chat_sample}", sample)
    )
    model = (config.get("model") or {}).get("model", "?")
    base_url = (config.get("model") or {}).get("base_url", "?")

    # json_mode=True 优先；部分供应商不支持 response_format，故失败后再用 json_mode=False 试一次
    raws: list[str] = []
    for json_mode in (True, False):
        try:
            raw = _chat(config, [{"role": "user", "content": prompt}], temperature=0.4, json_mode=json_mode, max_tokens=8000)
        except LLMError as e:
            raise DistillError(
                f"LLM 蒸馏失败（分析阶段）：{e}。"
                "国内网络请用 DeepSeek/通义/Kimi/智谱等国内直连模型（OpenAI 需要代理）"
            ) from e
        raws.append(raw or "")
        analysis = _parse_json_object(raw) if raw else None
        if analysis:
            return analysis

    _raise_parse_failure(raws, name, model, base_url)


def _raise_parse_failure(raws: list[str], name: str, model: str, base_url: str) -> None:
    """解析失败：把模型原始返回片段暴露给用户，定位"模型到底回了什么"。"""
    seen = [r.strip().replace("\n", " ") for r in raws if r and r.strip()]
    if not seen:
        reason = "模型两次都返回了空内容"
        hint = "说明请求可能未被真正计费/模型未产出文本（如触发思考模式、余额不足、模型名错误）"
    elif len(seen) == 1:
        reason = "模型返回空内容"
        hint = "同上：请确认调用记录、余额与模型名；国内网络请用 DeepSeek/通义/Kimi 等国内直连模型"
    else:
        reason = "模型返回的内容不是 JSON"
        hint = "若返回的是普通文字/报错/网页，说明命中的不是预期的 OpenAI 兼容接口"
    snippet = (seen[0] if seen else raws[0] if raws else "")[:160]
    raise DistillError(
        f"LLM 蒸馏失败（分析阶段）：{reason}。\n"
        f"请求：{base_url}/chat/completions，model={model}\n"
        f"模型原始返回开头：{snippet!r}\n"
        f"提示：{hint}。请把以上信息发给我定位。"
    )


def _build_pass(doc: PersonaDoc, analysis: dict, name: str, config: dict, manual_profile: str = "", correction_log: str = "") -> str | None:
    """Stage 2：基于分析 JSON 写出长 persona Markdown；失败返回 None（走结构化兜底）。

    撰写模型可用 [build] 段覆盖（更强模型），否则用主 [model]。
    """
    cfg = _build_config(config)
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
    prompt = (
        BUILD_PROMPT
        .replace("{name}", name)
        .replace("{manual_profile}", manual_profile or "（无）")
        .replace("{correction_log}", correction_log or "（暂无记录）")
        .replace("{analysis_json}", analysis_json)
    )
    try:
        text = _chat(cfg, [{"role": "user", "content": prompt}], temperature=0.7, max_tokens=8000)
    except LLMError:
        return None
    return text.strip() if text and text.strip() else None


def distill(messages: list[Message], name: str, config: dict, manual_profile: str = "", corrections: list[str] | None = None) -> PersonaDoc:
    """入口：两阶段蒸馏（对齐 dot-skill：手动画像优先 + 交互校正）。

    - manual_profile：用户手动画像/性格标签（最高优先级，进 analyze 与 build）。
    - corrections：用户纠正列表（dot-skill 校正层；进 analyze 镜头与 build 的 Correction 记录）。
    """
    if not messages:
        raise DistillError(
            "没有可分析的聊天消息：文件可能为空，或格式不是 WeFlow JSON / 微信 txt。"
        )
    api_key = (config.get("model") or {}).get("api_key")
    if not api_key:
        raise DistillError(
            "未配置模型 API key。请配置 .alchemy-hive/config.toml 的 [model] api_key，"
            "或使用 `alchemy-hive gui` 在界面中填写。"
        )
    corrections = list(corrections or [])
    fix = corrections[-1] if corrections else ""
    correction_log = ("用户纠正：" + "；".join(corrections)) if corrections else ""

    analysis = _analyze_pass(messages, name, config, manual_profile=manual_profile, fix=fix)  # 失败时已抛 DistillError

    data = dict(analysis)
    data["name"] = name                      # 强制参数名
    data.setdefault("display_name", name)    # 有则用模型的，无则用参数
    clean = {k: v for k, v in data.items() if k in PersonaDoc.model_fields}
    try:
        doc = PersonaDoc(**clean)
    except Exception:
        doc = PersonaDoc(name=name, display_name=data.get("display_name", name))

    # 把分析的记忆映射进 PersonaDoc.memory（.agent.json 记忆段 + build 兜底共用）
    memories = analysis.get("memories") or []
    doc.memory = [
        {"slug": m.get("slug", "core"), "body": m.get("body", str(m))}
        for m in memories if isinstance(m, dict)
    ]
    doc.manual_profile = manual_profile
    doc.corrections = corrections

    persona_text = _build_pass(doc, analysis, name, config, manual_profile=manual_profile, correction_log=correction_log)
    if persona_text:
        doc.system_prompt = persona_text
    else:
        doc.system_prompt = build_system_prompt(doc, data)  # 兜底：结构化渲染，保证非空
    return doc
