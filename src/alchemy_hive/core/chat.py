"""本地聊天测试：加载蒸馏出的 persona，与 LLM 进行多轮对话验证效果。"""
import json
from pathlib import Path

from .models import PersonaDoc
from .llm import chat_completion, LLMError


class ChatSession:
    """多轮对话会话：维护 system_prompt + 对话历史。"""

    def __init__(self, system_prompt: str, config: dict, name: str = ""):
        self.system_prompt = system_prompt
        self.config = config
        self.name = name
        self.history: list[dict] = []

    def send(self, message: str, temperature: float = 0.7) -> str:
        """发送消息并返回回复。"""
        self.history.append({"role": "user", "content": message})
        messages = [{"role": "system", "content": self.system_prompt}] + self.history
        try:
            reply = chat_completion(
                self.config, messages, temperature=temperature, max_retries=1, timeout=60
            )
        except LLMError:
            # 回退：移除最后一条 user 消息，避免历史污染
            self.history.pop()
            raise
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        """清空对话历史。"""
        self.history.clear()


def load_persona(persona_path: str | Path) -> PersonaDoc:
    """从 persona JSON 加载 PersonaDoc。"""
    p = Path(persona_path)
    return PersonaDoc.model_validate(json.loads(p.read_text(encoding="utf-8")))


def create_session(persona_path: str | Path, config: dict) -> ChatSession:
    """从 persona 文件创建聊天会话。"""
    doc = load_persona(persona_path)
    return ChatSession(
        system_prompt=doc.system_prompt,
        config=config,
        name=doc.display_name or doc.name,
    )
