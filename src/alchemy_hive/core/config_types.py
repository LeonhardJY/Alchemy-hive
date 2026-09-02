"""配置类型定义：为 config dict 提供类型标注。"""
from typing import TypedDict


class ModelConfig(TypedDict, total=False):
    """[model] 段配置。"""
    base_url: str
    api_key: str
    model: str


class BuildConfig(TypedDict, total=False):
    """[build] 段配置（撰写阶段可选覆盖）。"""
    base_url: str
    api_key: str
    model: str


class SamplingConfig(TypedDict, total=False):
    """[sampling] 段配置（控制分析阶段的消息采样量）。"""
    recent: int      # 近期消息数（默认 1500）
    early: int       # 早期消息数（默认 300）
    char_budget: int  # 总字符预算（默认 240K）
    per_msg_cap: int  # 单条消息截断上限（默认 1000）
    min_recent: int   # 预算收缩时近期保底条数（默认 50）


class BuzzConfig(TypedDict, total=False):
    """[buzz] 段配置（buzz-cli 直连建号）。"""
    channel: str
    relay_url: str


class AlchemyConfig(TypedDict, total=False):
    """Alchemy Hive 完整配置。"""
    model: ModelConfig
    build: BuildConfig
    sampling: SamplingConfig
    buzz: BuzzConfig
