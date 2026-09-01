"""蒸馏引擎（核心）：两阶段 LLM 蒸馏，对齐 dot-skill。

Stage 1 analyze：跨时间线抽样聊天 → LLM 输出结构化分析 JSON（性格/表达/情绪逻辑/20-40 条带原话的记忆）。
Stage 2 build：基于分析 JSON → LLM 写出 ≥400 行的完整角色 persona（Markdown），作为最终 system_prompt。
build 失败时降级为结构化渲染（build_system_prompt），绝不返回空。
"""
import json
import re
from pathlib import Path

from .models import Message, PersonaDoc
from .prompt import ANALYZE_PROMPT, BUILD_PROMPT, build_system_prompt
from .llm import chat_completion, LLMError


class DistillError(LLMError):
    """蒸馏失败：缺少模型配置或 LLM 调用失败。"""

# 默认配置路径（相对 CWD）；找不到时回退用户主目录，保证任意目录启动都能用同一份配置
DEFAULT_CONFIG_PATH = ".alchemy-hive/config.toml"


def resolve_config_path(path: str | None = None) -> str:
    """解析配置路径：存在即用；默认路径缺失时回退 ~/.alchemy-hive/config.toml。

    显式指定的自定义路径不回退（找不到时原样返回，由 load_config 按空配置处理），
    保证测试与 --config 指定行为可预期。
    """
    if path and Path(path).exists():
        return path
    home_cfg = Path.home() / ".alchemy-hive" / "config.toml"
    if (not path or path == DEFAULT_CONFIG_PATH) and home_cfg.exists():
        return str(home_cfg)
    return path or DEFAULT_CONFIG_PATH


def load_config(path: str | None) -> dict:
    """读 toml 配置；无文件返回空 dict。支持 .alchemy-hive/config.toml。"""
    import logging
    _log = logging.getLogger("alchemy_hive")
    if not path:
        return {}
    try:
        import tomllib  # py3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # py3.10 兼容
        except ModuleNotFoundError:
            _log.warning("config: tomllib/tomli 均不可用，跳过配置加载")
            return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open("rb") as f:
            return tomllib.load(f)
    except Exception as e:
        _log.warning("config: 解析 %s 失败: %s", path, e)
        return {}


# 样本策略（对齐 dot-skill：近期完整正文 + 早期抽样，不截断正文）
_SAMPLE_RECENT = 1500   # 近期完整消息数（覆盖当前关系动态）
_SAMPLE_EARLY = 300     # 早期消息数（覆盖共同记忆来源）
_PER_MSG_CAP = 1000     # 单条超长消息兜底截断（罕见），正文默认完整
_CHAR_BUDGET = 240_000  # 样本总字符预算：超了就动态减样本数，避免撞模型上下文上限（400）
_MIN_RECENT = 50        # 预算收缩时近期样本的保底条数（近期动态是画像主依据）


def _render_parts(msgs: list[Message], per_msg_cap: int) -> list[str]:
    parts = []
    for m in msgs:
        content = m.content or ""
        if per_msg_cap and len(content) > per_msg_cap:
            content = content[:per_msg_cap] + "…"
        parts.append(f"{m.timestamp} {m.sender}: {content}")
    return parts


def _sample_text(messages: list[Message], recent: int = _SAMPLE_RECENT, early: int = _SAMPLE_EARLY,
                 per_msg_cap: int = _PER_MSG_CAP, char_budget: int = _CHAR_BUDGET) -> str:
    """近期完整 + 早期抽样；正文不截断（仅单条超长时兜底截断）。

    总字符超预算时动态缩减样本数（先丢早期、再对半减近期，至少留 _MIN_RECENT 条），
    避免大聊天记录撞模型上下文上限。
    """
    splittable = len(messages) > recent
    if splittable:
        picked = messages[:early] + messages[-recent:]
    else:
        picked = list(messages)
    parts = _render_parts(picked, per_msg_cap)
    total = sum(len(p) for p in parts)
    recent_n = min(recent, len(messages))
    early_n = len(picked) - recent_n if splittable else 0
    while splittable and total > char_budget:
        if early_n > 0:
            early_n = 0                          # 先丢早期抽样
        elif recent_n > _MIN_RECENT:
            recent_n = max(_MIN_RECENT, recent_n // 2)  # 再对半减近期
        else:
            break                                # 已到底仍超：交给模型侧报错，不再阉割
        picked = (messages[:early_n] if early_n else []) + messages[-recent_n:]
        parts = _render_parts(picked, per_msg_cap)
        total = sum(len(p) for p in parts)
    return "\n".join(parts)


def _parse_json_object(content: str) -> dict | None:
    """从 LLM 响应中提取 JSON 对象。

    策略：
    1. 直接 json.loads（LLM 有时返回纯 JSON）
    2. 找最外层 {…}（可能被 ```json``` 包裹）再 parse
    不再用正则全局替换反引号，避免误伤 JSON 内容。
    """
    text = content.strip()
    # 直接尝试
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except (ValueError, TypeError):
        pass
    # 去掉 markdown 代码围栏再试：只剥离首尾的 ```json / ```，不去动内容
    stripped = text
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
    if stripped.endswith("```"):
        stripped = stripped[:-3].rstrip("\n")
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except (ValueError, TypeError):
        pass
    return None


def _chat(config: dict, messages: list[dict], *, temperature: float, json_mode: bool = False, max_tokens: int | None = None, timeout: float = 180) -> str:
    """带 max_tokens 上限的 LLM 调用：供应商拒绝 max_tokens（400）时去掉再试；
    网络类错误（超时/无法连接）立即抛出让上层暴露，不做无意义重试。失败抛 LLMError。"""
    attempts = [{"max_tokens": max_tokens}, {}] if max_tokens else [{}]
    last_error: LLMError | None = None
    for kwargs in attempts:
        try:
            return chat_completion(config, messages, temperature=temperature, json_mode=json_mode, max_retries=1, timeout=timeout, **kwargs)
        except LLMError as e:
            if getattr(e, "error_type", "") in ("timeout", "connect"):
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
            "没有可分析的聊天消息：文件可能为空，或不是支持的导出格式"
            "（微信 WeFlow JSON / 微信 txt / Telegram / WhatsApp / Instagram·Facebook）。"
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

    # 记录最后处理时间戳（增量蒸馏用）
    if messages:
        timestamps = [m.timestamp for m in messages if m.timestamp]
        if timestamps:
            doc.last_distill_ts = max(timestamps)

    return doc


def distill_incremental(messages: list[Message], name: str, config: dict,
                        existing_doc: PersonaDoc, manual_profile: str = "",
                        corrections: list[str] | None = None, workdir: str = "") -> PersonaDoc:
    """增量蒸馏：基于已有 persona + 新消息，合并分析结果。

    策略：
    1. 从已有 persona 提取最后时间戳，过滤新消息
    2. 对新消息做 analyze（带上旧 persona 摘要作为参考上下文）
    3. 合并新旧分析结果（记忆去重、规则合并）
    4. 重新执行 build 生成更新后的 persona
    """
    if not messages:
        raise DistillError("没有新消息可增量蒸馏")

    api_key = (config.get("model") or {}).get("api_key")
    if not api_key:
        raise DistillError("未配置模型 API key")

    # 从已有 persona 提取最后时间戳
    last_ts = _extract_last_timestamp(existing_doc, workdir=workdir, name=name)
    if last_ts:
        new_msgs = [m for m in messages if m.timestamp and m.timestamp > last_ts]
    else:
        new_msgs = messages

    if not new_msgs:
        # 没有新消息，直接返回已有 persona
        return existing_doc

    # 合并 corrections
    corrections = list(corrections or [])
    all_corrections = list(existing_doc.corrections or []) + corrections
    fix = corrections[-1] if corrections else ""
    correction_log = ("用户纠正：" + "；".join(all_corrections)) if all_corrections else ""

    # 构建旧 persona 摘要作为上下文
    old_summary = _build_persona_summary(existing_doc)

    # Analyze 新消息（带上旧 persona 参考）
    sample = _sample_text(new_msgs)
    prompt = (
        ANALYZE_PROMPT
        .replace("{name}", name)
        .replace("{manual_profile}", manual_profile or existing_doc.manual_profile or "（用户未提供）")
        .replace("{fix}", fix or "（无）")
        .replace("{count}", str(len(new_msgs)))
        .replace("{chat_sample}", sample)
    )
    # 在 prompt 末尾注入旧 persona 参考
    prompt += f"\n\n【已有 persona 摘要】（参考，保持一致性）：\n{old_summary}"

    model = (config.get("model") or {}).get("model", "?")
    base_url = (config.get("model") or {}).get("base_url", "?")

    raws: list[str] = []
    for json_mode in (True, False):
        try:
            raw = _chat(config, [{"role": "user", "content": prompt}], temperature=0.4, json_mode=json_mode, max_tokens=8000)
        except LLMError as e:
            raise DistillError(f"LLM 蒸馏失败（增量分析阶段）：{e}") from e
        raws.append(raw or "")
        analysis = _parse_json_object(raw) if raw else None
        if analysis:
            break
    else:
        _raise_parse_failure(raws, name, model, base_url)

    # 合并新旧分析结果
    merged = _merge_analysis(existing_doc, analysis, name)

    # Build 阶段
    cfg = _build_config(config)
    merged_json = json.dumps(merged, ensure_ascii=False, indent=2)
    build_prompt = (
        BUILD_PROMPT
        .replace("{name}", name)
        .replace("{manual_profile}", manual_profile or existing_doc.manual_profile or "（无）")
        .replace("{correction_log}", correction_log or "（暂无记录）")
        .replace("{analysis_json}", merged_json)
    )
    # 注入旧 persona 作为参考
    build_prompt += f"\n\n【已有 persona】（保持风格一致，更新内容）：\n{existing_doc.system_prompt[:2000]}"

    try:
        persona_text = _chat(cfg, [{"role": "user", "content": build_prompt}], temperature=0.7, max_tokens=8000)
    except LLMError:
        persona_text = None

    # 构建更新后的 doc
    data = dict(merged)
    data["name"] = name
    data.setdefault("display_name", name)
    clean = {k: v for k, v in data.items() if k in PersonaDoc.model_fields}
    try:
        doc = PersonaDoc(**clean)
    except Exception:
        doc = PersonaDoc(name=name, display_name=name)

    memories = merged.get("memories") or []
    doc.memory = [
        {"slug": m.get("slug", "core"), "body": m.get("body", str(m))}
        for m in memories if isinstance(m, dict)
    ]
    doc.manual_profile = manual_profile or existing_doc.manual_profile
    doc.corrections = all_corrections

    if persona_text:
        doc.system_prompt = persona_text
    else:
        doc.system_prompt = build_system_prompt(doc, data)

    return doc


def _extract_last_timestamp(doc: PersonaDoc, workdir: str = "", name: str = "") -> str | None:
    """提取最后处理时间戳：优先从 persona 的 last_distill_ts 字段取，回退到记忆文本正则。"""
    # 优先方案：从 persona 元数据取（最可靠）
    if doc.last_distill_ts:
        return doc.last_distill_ts
    # 回退：从记忆文本正则提取（不可靠，但兜底）
    import re
    last_ts = ""
    for m in doc.memory:
        if isinstance(m, dict):
            body = m.get("body", "")
            match = re.search(r"(\d{4}-\d{2}-\d{2})", body)
            if match and match.group(1) > last_ts:
                last_ts = match.group(1)
    return last_ts if last_ts else None


def _build_persona_summary(doc: PersonaDoc) -> str:
    """构建 persona 摘要（用于注入增量分析 prompt）。"""
    parts = []
    if doc.relationship:
        parts.append(f"关系：{doc.relationship}")
    if doc.expression_rules:
        parts.append("表达规则：" + "；".join(doc.expression_rules[:5]))
    if doc.signature_phrases:
        parts.append("口头禅：" + "、".join(doc.signature_phrases[:5]))
    if doc.memory:
        recent = doc.memory[-5:]
        parts.append("近期记忆：" + "；".join(
            m.get("body", "") for m in recent if isinstance(m, dict)
        ))
    return "\n".join(parts) or "（无）"


def _merge_analysis(existing_doc: PersonaDoc, new_analysis: dict, name: str) -> dict:
    """合并新旧分析结果。带上限防止无限膨胀。"""
    _MAX_MEMORIES = 60
    _MAX_RULES = 30
    _MAX_PHRASES = 20
    _MAX_REPLIES_SCENES = 15

    merged = dict(new_analysis)
    merged["name"] = name
    merged.setdefault("display_name", name)

    # 合并 memories：追加新记忆，去重旧记忆，带上限
    old_memories = list(existing_doc.memory or [])
    new_memories = new_analysis.get("memories") or []
    seen_slugs = {m.get("slug") for m in old_memories if isinstance(m, dict)}
    for m in new_memories:
        if isinstance(m, dict) and m.get("slug") not in seen_slugs:
            old_memories.append(m)
            seen_slugs.add(m.get("slug"))
    merged["memories"] = old_memories[-_MAX_MEMORIES:]  # 保留最近的

    # 合并 expression_rules：追加新规则，带上限
    old_rules = list(existing_doc.expression_rules or [])
    new_rules = new_analysis.get("expression_rules") or []
    merged["expression_rules"] = (old_rules + [r for r in new_rules if r not in old_rules])[-_MAX_RULES:]

    # 合并 signature_phrases：合并去重，带上限
    old_phrases = set(existing_doc.signature_phrases or [])
    new_phrases = new_analysis.get("signature_phrases") or []
    merged["signature_phrases"] = list(old_phrases | set(new_phrases))[-_MAX_PHRASES:]

    # example_replies：追加新场景，覆盖旧场景，带上限
    old_replies = dict(existing_doc.example_replies or {})
    new_replies = new_analysis.get("example_replies") or {}
    old_replies.update(new_replies)
    # 截断到上限
    if len(old_replies) > _MAX_REPLIES_SCENES:
        old_replies = dict(list(old_replies.items())[-_MAX_REPLIES_SCENES:])
    merged["example_replies"] = old_replies

    # 保留旧的 relationship 信息（如果新分析没有提供）
    for field in ("relationship", "relationship_context", "relationship_arc", "relationship_essence"):
        if not merged.get(field) and getattr(existing_doc, field, None):
            merged[field] = getattr(existing_doc, field)

    return merged
