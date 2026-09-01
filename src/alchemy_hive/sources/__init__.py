"""聊天源解析适配器：自动注册所有内置 source adapter。"""
from .weflow import WeflowSource
from .wechat import WechatSource
from .telegram import TelegramSource
from .whatsapp import WhatsappSource
from .meta import MetaSource
from .discord import DiscordSource
from .slack import SlackSource
from .imessage import ImessageSource
from .qq import QQSource
from .generic import GenericSource
from ..core.plugins import register_source

# 自动注册所有内置 source adapter（generic 必须最后注册，作为兜底）
for _adapter in [WeflowSource(), WechatSource(), TelegramSource(),
                 WhatsappSource(), MetaSource(),
                 DiscordSource(), SlackSource(), ImessageSource(), QQSource(),
                 GenericSource()]:
    register_source(_adapter)
