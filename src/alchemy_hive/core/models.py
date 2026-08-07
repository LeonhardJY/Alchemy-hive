"""中立数据模型：解析与蒸馏共用，不依赖任何平台。"""
from pydantic import BaseModel


class Message(BaseModel):
    """一条聊天消息。"""
    sender: str          # 发送者显示名，用户本人约定为 "我"
    content: str         # 文本内容（过滤图片/表情/链接等非文本占位后）
    timestamp: str       # "YYYY-MM-DD HH:MM:SS"


class PersonaDoc(BaseModel):
    """蒸馏产出的中立人物档案（对齐 dot-skill 多层 persona + 交互校正）。"""
    name: str
    display_name: str
    relationship: str = ""
    relationship_context: str = ""   # 这段关系由什么定义
    relationship_arc: str = ""       # 这段关系的来龙去脉（怎么认识/发展/转折/现在）
    relationship_essence: str = ""   # 这段关系对他意味着什么（总结性）
    profile: dict = {}
    expression_rules: list[str] = []
    signature_phrases: list[str] = []
    rhythm: str = ""                 # 说话节奏一句话
    example_replies: dict = {}   # {场景: [真实例句]}
    memory: list[dict] = []      # [{slug, body}]
    layers: dict = {}            # closeness/withdrawal/conflict/repair/boundaries/care
    memory_signature: str = ""   # 一段关系的记忆余像
    manual_profile: str = ""     # 用户手动画像（性格标签等，最高优先级）
    corrections: list[str] = []  # 用户纠正记录（dot-skill correction 层）
    system_prompt: str = ""      # 生成后的完整 persona prompt 文本
