"""蒸馏 prompt 模板（对齐 dot-skill 的两阶段：analyzer 分析 → builder 撰写长 persona）。

流程：analyze（JSON 结构化分析 + 大量带原话的记忆）→ build（纯 Markdown 写出 400+ 行角色 persona）。
build_system_prompt 仅在 build 阶段失败时作结构化兜底渲染。
"""

ANALYZE_PROMPT = """你是一个人类分析师。目标是把 {name} 蒸馏成有"活人感"的人物画像。

【用户手动画像】（用户提供，**最高优先级**；与聊天记录冲突时以手动为准，并在输出中注明）：
{manual_profile}

【用户纠正】（用户对上一版不满意，本次务必优先遵循）：{fix}

下面是 {name} 与对话对象的微信聊天记录（近期完整消息 + 早期抽样，正文未截断）。

请深度分析 {name}，输出一个 JSON：
- display_name: {name}
- relationship: 一句话描述他与对话对象的关系
- relationship_context: 3-5 句，这段关系由什么定义（共同经历、相处方式、当前状态、发生过的重要事）
- relationship_arc: 5-8 句，这段关系的来龙去脉，像讲一个小故事（怎么认识、怎么熟起来、关键转折、一起经历的事、现在变成什么样），要有时间感和温度
- relationship_essence: 3-4 句，这段关系对 {name} 来说意味着什么（总结性判断：他把对方当什么、这段关系的底色、他在对方心里的位置）
- profile: 对象，含 gender（性别，未知写"未知"）、mbti（未知写"未知"）、
    tags（6-10 个性格关键词，**优先来自手动画像**）、key_traits（数组，每项 {trait, behavior, example_quote}，
    behavior 是"在什么情况下他会怎么做"的具体描述，example_quote 是聊天原话）
- expression_rules: 8-12 条表达硬规则，每条必须是"在什么情况下他会怎么说/怎么做"的具体行为并附原话例证；
    **手动画像里的性格标签必须翻译成具体行为规则**（如"甩锅高手"→"出问题第一句先说需求没说清楚"）
- signature_phrases: 高频口头禅/语气词/反应词（必须摘自原话）
- rhythm: 2-3 句描述说话节奏（短句/长句、连发习惯、回复速度、切换场景时的变化）
- speaking_pattern: 2-3 句（句式特征、emoji 使用、标点密度、正式程度）
- example_replies: 对象，键是场景（约饭/惊讶/状态不好/给建议/认真讨论/玩游戏/吐槽/分享/关心/怼人/沉默 等，按内容灵活取），
    每个场景 3-8 条真实原话（必须一字不改摘自聊天记录）
- layers: 对象（都基于记录推断，各 3-5 句并附例证）：
    closeness（亲近放松时怎样）、withdrawal（回避/不安全时怎样）、conflict（冲突时怎样）、
    repair（怎么修复关系）、boundaries（边界/雷区）、care（怎么表达关心）
- memories: 共同回忆条目数组，提取 **20-40 条**（宁多勿少），每条：
    {slug: "core" 或 "mem/记忆名", body: 回忆的一句话（谁/何时/哪件事，具体）, quote: 聊天里最相关的一句原话, trigger: 提起这个话题的场景或触发词, significance: 这段回忆对这段关系意味着什么（1-2 句总结）}
- memory_signature: 一句最能概括这段关系余味的话

要求：
1. 所有 quote/例句/口头禅必须一字不改引用聊天原话，禁止编造。
2. 手动画像优先：标签要翻译成"什么情况下怎么做"的具体行为规则。
3. 记忆要具体到人和事，不要空泛（如"一起吃饭"不行，"每周五在食堂二楼靠窗研究菜单"可以）。
4. 只输出 JSON，不要其它文字。

聊天记录（{count} 条，近期完整 + 早期抽样）：
{chat_sample}
"""

BUILD_PROMPT = """你是一位角色塑造师。为 {name} 撰写一份完整、鲜活的角色 persona，**纯 Markdown 输出，至少 400 行**，不要输出任何多余说明。

【用户手动画像】（写进 persona 并优先体现）：{manual_profile}

要求：
- 写得具体、有血有肉、像真人，禁止空泛形容词（如"他很好""他很幽默"）。
- **不要写成标签/简历/规则列表**——要写出一个有温度、有来龙去脉的真人，和你们这段关系到底有多重。
- 全部基于分析结果里的原话、记忆和行为描述；例句必须一字不改引用原话。
- 手动画像标签要体现为 Layer 0 的具体行为规则。
- 结构严格按下面的模板，每一节都要写满（字号越大越要写多）：

# {name} — Persona

## Layer 0 核心性格（最高优先级）
写 12-18 条具体规则，格式统一为"在什么情况下，他会怎么做"，每条 1-2 句，尽量附原话例证。

## Layer 1 身份与关系
身份、与对方的关系、这段关系由什么定义、当前状态。4-6 句。

## 这段关系 · 一路走来
把分析里的 relationship_arc 扩写成 10-15 句流畅的散文：怎么认识、怎么一步步熟起来、中间的关键转折、一起扛过/乐过的事、现在变成了什么样。要有时间线、有具体事件、有温度——读起来像在讲一段真实的关系，而不是简历。

## 这段关系意味着什么
把 analysis 里的 relationship_essence 扩写成 5-8 句总结性话语：他把对方当什么人、这段关系的底色是什么、他在对方心里的位置、如果这段关系会留下一句话，会是什么。这些话要"一句话能说透这段关系"。

## Layer 2 表达风格
### 口头禅与高频词
列出并说明什么时候用。
### 说话节奏与句式
节奏、句长、emoji、标点、正式程度，各 2-3 句。
### 你会怎么说（大量直接例子）
写 15-25 组，格式：
> 场景：xxxx
> {name}：原话

## Layer 3 情绪逻辑
### 什么时候打开话匣子
### 什么时候回避
### 他怎么表达关心
### 他怎么守护自己
每节 3-5 句，附原话。

## Layer 4 冲突与修复
### 冲突方式
### 沉默与消失
### 修复方式
### 边界与雷区
每节 3-5 句，附原话。

## Layer 5 记忆库
把分析结果里的每一条记忆展开成一个小节（20-40 节，写满，宁多勿少）：
### 记忆 N：{记忆名}
- 一句话：{body}
- 聊天原话：{quote}
- 触发话题：{trigger}
- 关系意义：{significance}
每条记忆 5-10 行，写得具体、有画面、有它在这段关系里的分量。

## 记忆余像
用 100 字以内、一句最有分量的话收尾——点透这段关系的本质（总结性话语，浓缩你和 {name} 的全部）。

## Correction 记录
{correction_log}

分析结果（原话/记忆/行为）：
{analysis_json}
"""


# layers 渲染顺序与中文标签（结构化兜底渲染用）
_LAYER_LABELS = (
    ("closeness", "亲近时"),
    ("withdrawal", "回避时"),
    ("conflict", "冲突时"),
    ("repair", "修复"),
    ("boundaries", "边界"),
    ("care", "关心时"),
)


def build_system_prompt(doc, data: dict) -> str:
    """把蒸馏出的结构化字段渲染成 persona system_prompt（兜底：build 阶段失败时用）。

    结构对齐 dot-skill 的 PART B；data 为 LLM 分析输出，doc 提供缺省回退；缺失段落自动省略。
    """
    name = doc.display_name or doc.name
    relationship = data.get("relationship") or doc.relationship or ""
    context = data.get("relationship_context") or doc.relationship_context or ""
    arc = data.get("relationship_arc") or doc.relationship_arc or ""
    essence = data.get("relationship_essence") or doc.relationship_essence or ""
    rules = data.get("expression_rules") or doc.expression_rules or []
    phrases = data.get("signature_phrases") or doc.signature_phrases or []
    rhythm = data.get("rhythm") or doc.rhythm or ""
    repls = data.get("example_replies") or doc.example_replies or {}
    layers = data.get("layers") or doc.layers or {}
    # analyze 输出键是 memories；兼容旧产物的 memory 键，最后回退 doc.memory
    memories = data.get("memories") or data.get("memory") or doc.memory or []
    mem_sig = data.get("memory_signature") or doc.memory_signature or ""

    lines = [f"你是{name}。" + (relationship if relationship else "")]
    if context:
        lines.extend(["", context])
    if arc:
        lines.extend(["", "# 这段关系 · 一路走来", arc])
    if essence:
        lines.extend(["", "# 这段关系意味着什么", essence])
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
