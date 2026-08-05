"""蒸馏 prompt 模板（对齐 dot-skill 的多层 persona 结构）与 system_prompt 生成器。"""

DISTILL_PROMPT = """你是一个人类分析师。下面是 {name} 与对话对象的微信聊天记录。

请分析 {name} 这个人，输出一个 JSON，字段如下：
- display_name: {name}
- relationship: 一句话描述他与对话对象的关系
- relationship_context: 2-3 句，这段关系由什么定义（共同经历、当前状态、相处方式）
- profile: 对象，含 gender（性别，未知写"未知"）、mbti（未知写"未知"）、tags（性格关键词数组）
- expression_rules: 4-6 条表达硬规则，必须具体可执行（"在什么情况下会怎么说"），
  从聊天记录归纳他的真实说话方式（如"一次只说一句话""分享链接只配一句感叹"），
  禁止写形容词（如"他很幽默"），要能防止 AI 输出书面语
- signature_phrases: 高频口头禅/语气词/反应词列表（必须摘自聊天记录原话）
- rhythm: 一句话描述他的说话节奏（如"短句碎片连发，分享时一条链接配一句感叹"）
- example_replies: 对象，键是场景（约饭/惊讶/状态不好/给建议/认真讨论等，按聊天内容灵活取），
  值是真实聊天原话数组（必须一字不改摘自聊天记录，不要编造）
- layers: 对象，5 个键（都基于聊天记录推断，各 1-2 句）：
    closeness: 他感到亲近/放松时怎么表现
    withdrawal: 他不安全/回避/不想聊时怎么表现
    conflict: 冲突时怎么表现
    repair: 他怎么修复关系
    boundaries: 他的边界/雷区
- memory: 共同回忆条目数组 [{slug, body}]，slug 用 "core"(最重要) 或 "mem/回忆名"，
  body 是回忆的一句话（摘自聊天记录）
- memory_signature: 一句最能概括这段关系余味的话

要求：
1. 所有例句/口头禅/记忆必须直接引用聊天记录原话，禁止编造。
2. 表达规则要具体到"什么情况下怎么做"，能防书面语。
3. 只输出 JSON，不要其它文字。

聊天记录：
{chat_sample}
"""


# layers 渲染顺序与中文标签
_LAYER_LABELS = (
    ("closeness", "亲近时"),
    ("withdrawal", "回避时"),
    ("conflict", "冲突时"),
    ("repair", "修复"),
    ("boundaries", "边界"),
)


def build_system_prompt(doc, data: dict) -> str:
    """把蒸馏出的结构化字段渲染成最终 persona system_prompt。

    结构对齐 dot-skill 的 PART B（表达硬规则/口头禅/节奏/场景例句/情绪逻辑/共同回忆/记忆余像）。
    data 为 LLM 原始输出，doc 提供缺省回退；缺失的段落自动省略。
    """
    name = doc.display_name or doc.name
    relationship = data.get("relationship") or doc.relationship or ""
    context = data.get("relationship_context") or doc.relationship_context or ""
    rules = data.get("expression_rules") or doc.expression_rules or []
    phrases = data.get("signature_phrases") or doc.signature_phrases or []
    rhythm = data.get("rhythm") or doc.rhythm or ""
    repls = data.get("example_replies") or doc.example_replies or {}
    layers = data.get("layers") or doc.layers or {}
    memories = data.get("memory") or doc.memory or []
    mem_sig = data.get("memory_signature") or doc.memory_signature or ""

    lines = [f"你是{name}。" + (relationship if relationship else "")]
    if context:
        lines.extend(["", context])
    lines.append("")
    lines.append("# 表达硬规则（最高优先级，违反就不像）")
    for r in rules:
        lines.append(f"- {r}")
    if phrases:
        lines.extend(["", "# 高频口头禅/语气词"])
        for w in phrases:
            lines.append(f"- {w}")
    if rhythm:
        lines.extend(["", "# 说话节奏", rhythm])
    if repls:
        lines.extend(["", "# 场景例句（全部摘自真实聊天记录）"])
        for scene, scene_lines in repls.items():
            lines.append(f"## {scene}")
            for line in (scene_lines if isinstance(scene_lines, list) else [scene_lines]):
                lines.append(f"- {line}")
    if layers:
        lines.extend(["", "# 情绪逻辑"])
        for key, label in _LAYER_LABELS:
            value = layers.get(key) if isinstance(layers, dict) else None
            if value:
                lines.append(f"- {label}：{value}")
    if memories:
        lines.extend(["", "# 共同回忆"])
        for m in memories:
            if isinstance(m, dict):
                lines.append(f"- {m.get('body', str(m))}")
    if mem_sig:
        lines.extend(["", "# 记忆余像", mem_sig])
    return "\n".join(lines)
