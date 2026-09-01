"""buzz .agent.json 导出：封装现有的 write_snapshot_json。"""
from ..buzz.snapshot import write_snapshot_json


class BuzzExporter:
    """导出为 buzz-agent-snapshot v1 格式（.agent.json）。"""
    name = "buzz"
    extension = ".agent.json"
    label = "buzz (.agent.json)"

    def export(self, doc, out_dir: str, **kwargs) -> str:
        include_memory = kwargs.get("include_memory", False)
        return write_snapshot_json(doc, out_dir, include_memory=include_memory)
