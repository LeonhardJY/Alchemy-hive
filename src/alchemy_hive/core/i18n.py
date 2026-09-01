"""i18n 工具函数：多模块共用的 _t() 翻译辅助。"""


def t(lang: str, key: str, messages: dict, **kw) -> str:
    """按语言从消息字典取值并格式化。messages 形如 {"zh": {"key": "值"}, "en": {...}}。"""
    return messages.get(lang, messages.get("zh", {}))[key].format(**kw)
