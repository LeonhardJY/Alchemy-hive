"""中立数据模型：解析与蒸馏共用，不依赖任何平台。"""
from pydantic import BaseModel


class Message(BaseModel):
    """一条聊天消息。"""
    sender: str          # 发送者显示名，用户本人约定为 "我"
    content: str         # 文本内容（过滤图片/表情/链接等非文本占位后）
    timestamp: str       # "YYYY-MM-DD HH:MM:SS"


class PersonaDoc(BaseModel):
    """蒸馏产出的中立人物档案（M1 先支持字段，蒸馏任务再填充）。"""
    name: str
    display_name: str
    relationship: str = ""
    profile: dict = {}
    expression_rules: list[str] = []
    signature_phrases: list[str] = []
    example_replies: dict = {}   # {场景: [真实例句]}
    memory: list[dict] = []      # [{slug, body}]
    layers: dict = {}            # closeness/withdrawal/conflict/repair/boundaries
    system_prompt: str = ""      # 生成后的完整 persona prompt 文本
