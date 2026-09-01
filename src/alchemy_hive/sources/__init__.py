"""聊天源解析适配器：自动注册所有内置 source adapter。"""
from .weflow import WeflowSource
from .wechat import WechatSource
from .telegram import TelegramSource
from .whatsapp import WhatsappSource
from .meta import MetaSource
from .generic import GenericSource
from ..core.plugins import register_source

# 自动注册所有内置 source adapter
for _adapter in [WeflowSource(), WechatSource(), TelegramSource(),
                 WhatsappSource(), MetaSource(), GenericSource()]:
    register_source(_adapter)
