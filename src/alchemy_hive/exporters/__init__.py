"""导出适配器：多格式导出。自动注册所有内置 exporter。"""
from .text import TextExporter
from .buzz_exporter import BuzzExporter
from .sillytavern import SillyTavernExporter
from .coze import CozeExporter
from .dify import DifyExporter
from ..core.plugins import register_exporter

# 自动注册所有内置 exporter
register_exporter(TextExporter())
register_exporter(BuzzExporter())
register_exporter(SillyTavernExporter())
register_exporter(CozeExporter())
register_exporter(DifyExporter())
