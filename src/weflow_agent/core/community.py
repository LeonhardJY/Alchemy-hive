"""社群清单生成：把多个已蒸馏人物组织成 buzz 群组引导。"""
from ..core.safe import safe_filename


def build_agents_manifest(names: list[str], export_dir: str, channel: str = "#friends") -> list[dict]:
    """每个 agent 的社群条目：路径用 safe 名，subscribe/triggers 为群组建议。"""
    agents = []
    for name in names:
        safe = safe_filename(name)
        agents.append({
            "name": name,
            "displayName": name,
            "agentJson": f"{export_dir}/{safe}.agent.json",
            "subscribe": [channel],
            "triggers": [f"@{name}", name],
            "summary": "",  # 可选：后续从 persona 提取一句话
        })
    return agents


def build_community(names: list[str], export_dir: str, channel: str = "#friends") -> dict:
    """社群配置清单：群名建议、agent 列表、setup 步骤。"""
    return {
        "community": f"{channel.strip('#')} 群",
        "channel": channel,
        "agents": build_agents_manifest(names, export_dir, channel),
        "setup_steps": [
            f"1. 把 build/export/ 下的每个 .agent.json 拖入 buzz 桌面端 My Agents 导入",
            f"2. 在 buzz 新建频道 {channel} 并把以上 agent 加入",
            f"3. 在群里 @agent 的名字触发对话；subscribe/triggers 是建议，导入后可在 buzz UI 微调",
        ],
    }
