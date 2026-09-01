"""纯文本 system prompt 导出：最通用的格式，几乎所有 agent 平台都支持。"""
from pathlib import Path

from ..core.safe import safe_filename


class TextExporter:
    """导出 PersonaDoc 的 system_prompt 为纯文本文件（.txt）。

    用途：手动粘贴到 Claude Projects / OpenAI GPTs / 任意 agent 平台的 system prompt 字段。
    """
    name = "text"
    extension = ".txt"
    label = "System Prompt (.txt)"

    def export(self, doc, out_dir: str, **kwargs) -> str:
        p = Path(out_dir) / f"{safe_filename(doc.name)}.txt"
        p.write_text(doc.system_prompt or "", encoding="utf-8")
        return str(p)
