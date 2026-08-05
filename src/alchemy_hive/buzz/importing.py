"""把导出产物送到 buzz 桌面端：打开导出文件夹 + 复制文件完整路径到剪贴板。

buzz 桌面端（Tauri）目前只开放 UI 导入（My Agents → 导入 / 拖入窗口），
没有命令行或文件关联导入接口；buzz-cli 面向自建 relay 且需私钥，非桌面路径。
本模块把"找文件 + 复制路径"压成一步，并尽力触发默认打开。
"""
import os
import subprocess
from pathlib import Path

from ..core.safe import safe_filename


def _copy_to_clipboard(text: str) -> bool:
    """Windows 剪贴板：优先 clip.exe（utf-16le），失败返回 False。"""
    try:
        subprocess.run(["clip"], input=text.encode("utf-16le"), check=True, timeout=5, shell=True)
        return True
    except Exception:
        return False


def _open_folder(path: Path) -> bool:
    """打开文件夹：Windows 用 os.startfile，其他平台用 xdg-open/open。"""
    import sys
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=True, timeout=10)
        else:
            subprocess.run(["open", str(path)], check=True, timeout=10)
        return True
    except Exception:
        return False


def import_to_buzz(name: str, workdir: str = "build") -> list[str]:
    """打开导出文件夹 + 复制 .agent.json 完整路径，返回步骤日志。"""
    logs: list[str] = []
    export_dir = Path(workdir) / "export"
    safe = safe_filename(name)
    agent_file = export_dir / f"{safe}.agent.json"
    if not agent_file.exists():
        raise FileNotFoundError(f"未找到导出文件 {agent_file}，请先运行 export")

    logs.append(f"[buzz] 导出文件：{agent_file}")
    if _open_folder(export_dir):
        logs.append(f"[buzz] 已打开导出文件夹：{export_dir}")
    else:
        logs.append(f"[buzz] 无法自动打开文件夹，请手动前往 {export_dir}")

    if _copy_to_clipboard(str(agent_file.resolve())):
        logs.append("[buzz] 文件完整路径已复制到剪贴板")
    logs.append("[buzz] 在 buzz 桌面端 My Agents → 导入：粘贴路径，或把文件拖入窗口。")
    logs.append("[buzz] 提示：buzz 桌面端暂未开放命令行导入接口，此操作已把导入步骤压缩到最短。")
    return logs
