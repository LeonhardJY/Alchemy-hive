"""内置蒸馏 prompt 模板：要求模型从聊天记录提取表达规则与真实例句。"""

DISTILL_PROMPT = """你是一个对话风格分析师。下面是两个人的微信聊天记录。
请分析 {name} 这个人，输出一个 JSON，字段如下：
- display_name: {name}
- relationship: 一句话描述他与对话对象的关系
- expression_rules: 3-5 条表达硬规则（如"一次只说一句话""禁用书面语"）
- signature_phrases: 高频口头禅/语气词列表
- example_replies: 一个对象，键是场景（约饭/惊讶/状态不好/给建议），值是真实聊天原话列表（必须摘自聊天记录，不要编造）
- memory: 共同回忆条目列表 [{slug, body}]，slug 用 "core"（最重要的核心回忆）
  或 "mem/回忆名"（如 "mem/寺庙还愿"），body 是回忆一句话（摘自聊天记录）

要求：
1. 例句必须直接引用聊天记录原话。
2. 表达规则要能防止 AI 输出书面语。
3. 只输出 JSON，不要其它文字。

聊天记录：
{chat_sample}
"""
