"""把导出产物送到 buzz：一键导入 + 高容错。

傻瓜用户会犯的错，全部兜住：
- 忘了蒸馏/没有成品 → 友好提示"先开始蒸馏"，不报错
- 名称输错或没填 → 自动导入全部成品，并说明
- 剪贴板/打开文件夹失败 → 提示手动路径
- buzz-cli 直连建号缺配置 → 说明缺什么，仍用"打开文件夹+复制路径"主路径
"""
import json as _json
import os
import shutil
import subprocess
from pathlib import Path

from ..core.safe import safe_filename

# buzz-cli draft-create 的 system_prompt 上限（agent_management.rs: MAX_PROMPT_CHARS=20000）
_MAX_PROMPT = 19000

# 导入流程文案（GUI 按语言输出；默认中文与历史一致，测试锁定）
_L = {
    "zh": {
        "no_build_1": "[buzz] 还没有成品文件夹 build/export，说明还没蒸馏过。",
        "no_build_2": "[buzz] 请先在上面点「开始蒸馏」，成功后这里就会生成 .agent.json。",
        "no_export_1": "[buzz] 导出文件夹 build/export 是空的，还没有成品。",
        "no_export_2": "[buzz] 请先「开始蒸馏」生成人物，再回来点这个按钮。",
        "not_found_fmt": "[buzz] 没找到「{name}」的成品文件，但检测到 {n} 个，已全部帮你导入。",
        "not_found_hint": "[buzz] 想只导某一个？把名称栏填成对应名字再点一次即可。",
        "all_imported_fmt": "[buzz] 未填名称，检测到 {n} 个成品，已全部帮你导入（适配多人物社群）。",
        "opened_fmt": "[buzz] 已打开导出文件夹：{dir}",
        "open_fail_fmt": "[buzz] 未能自动打开文件夹，请手动前往：{dir}",
        "copied_fmt": "[buzz] 已把 {n} 个 .agent.json 的完整路径复制到剪贴板。",
        "copy_fail": "[buzz] 剪贴板复制失败，请手动复制上面的路径。",
        "guide_import": "[buzz] 导入：打开 buzz 桌面端 → My Agents → 导入 → 粘贴路径（或把文件拖进窗口）。",
        "guide_count_fmt": "[buzz] 共 {n} 个 agent；把多个拉进同一频道就是一个社群，想建几个建几个。",
        "draft_no_channel": "[buzz] 提示：未提供 --channel（高级直连建号需要它），跳过；用「打开文件夹+复制路径」即可。",
        "draft_no_cli": "[buzz] 提示：未检测到 buzz-cli（命令行 `buzz`），跳过直连建号；用「打开文件夹+复制路径」即可。",
        "draft_no_key": "[buzz] 提示：未设置 BUZZ_PRIVATE_KEY，跳过直连建号；桌面端用「打开文件夹+复制路径」导入即可。",
        "draft_ok_fmt": "[buzz] ✓ 已通过 buzz-cli 创建 agent 草稿：{name}（channel {channel}）",
        "draft_fail_fmt": "[buzz] buzz-cli 创建失败（exit {code}）：{err}",
        "draft_call_fail_fmt": "[buzz] buzz-cli 调用失败：{err}",
    },
    "en": {
        "no_build_1": "[buzz] No build/export folder yet — you haven't distilled anything.",
        "no_build_2": "[buzz] Click “Start distillation” above; the .agent.json will appear here.",
        "no_export_1": "[buzz] build/export is empty — no output yet.",
        "no_export_2": "[buzz] Run a distillation first, then come back.",
        "not_found_fmt": "[buzz] Couldn't find an output for “{name}”, but found {n} — imported them all for you.",
        "not_found_hint": "[buzz] Want just one? Fill the name field and click again.",
        "all_imported_fmt": "[buzz] No name given — found {n} outputs, imported them all (for multi-person communities).",
        "opened_fmt": "[buzz] Opened export folder: {dir}",
        "open_fail_fmt": "[buzz] Couldn't open the folder automatically — go to: {dir}",
        "copied_fmt": "[buzz] Copied full paths of {n} .agent.json to clipboard.",
        "copy_fail": "[buzz] Clipboard copy failed — copy the paths above manually.",
        "guide_import": "[buzz] To import: open buzz desktop → My Agents → Import → paste the path (or drag the file in).",
        "guide_count_fmt": "[buzz] {n} agent(s) total; drop them into one channel to build a community.",
        "draft_no_channel": "[buzz] Note: no --channel given (needed for direct create) — skipped; use “open folder + copy path” instead.",
        "draft_no_cli": "[buzz] Note: buzz-cli not found on PATH — skipped; use “open folder + copy path”.",
        "draft_no_key": "[buzz] Note: BUZZ_PRIVATE_KEY not set — skipped; desktop import still works.",
        "draft_ok_fmt": "[buzz] ✓ Created agent draft via buzz-cli: {name} (channel {channel})",
        "draft_fail_fmt": "[buzz] buzz-cli create failed (exit {code}): {err}",
        "draft_call_fail_fmt": "[buzz] buzz-cli call failed: {err}",
    },
}


def _t(lang: str, key: str, **kw) -> str:
    return _L.get(lang, _L["zh"])[key].format(**kw)


def _copy_to_clipboard(text: str) -> bool:
    """跨平台剪贴板：Windows 用 clip（utf-16le）、macOS 用 pbcopy、Linux 依次试
    wl-copy/xclip/xsel；任何一步失败返回 False（上层回退"手动复制路径"提示）。"""
    import sys
    try:
        if os.name == "nt":
            subprocess.run(["clip"], input=text.encode("utf-16le"), check=True, timeout=5)
            return True
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
            return True
        for cmd in ("wl-copy", "xclip", "xsel"):
            if shutil.which(cmd):
                args = [cmd] if cmd == "wl-copy" else (
                    [cmd, "-selection", "clipboard"] if cmd == "xclip" else [cmd, "--clipboard", "--input"])
                subprocess.run(args, input=text.encode("utf-8"), check=True, timeout=5)
                return True
        return False
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


def _list_exports(export_dir: Path) -> list[Path]:
    return sorted(export_dir.glob("*.agent.json")) if export_dir.exists() else []


def _display_name(agent_file: Path) -> str:
    """从文件名取人物名：'小明.agent.json' → '小明'（不能只 .stem，会剩 '.agent'）。"""
    name = agent_file.name
    return name[: -len(".agent.json")] if name.endswith(".agent.json") else agent_file.stem


def _system_prompt_of(agent_file: Path) -> str:
    """从 .agent.json 取 definition.systemPrompt 作为建号指令；损坏时退回文件原文。"""
    try:
        snap = _json.loads(agent_file.read_text(encoding="utf-8"))
        prompt = (snap.get("definition") or {}).get("systemPrompt") or ""
        if prompt:
            return prompt[: _MAX_PROMPT]
    except Exception:
        pass
    try:
        return agent_file.read_text(encoding="utf-8")[: _MAX_PROMPT]
    except Exception:
        return ""


def _find_buzz_cli() -> str | None:
    """定位 buzz-cli：优先 PATH；否则找桌面端自带二进制（Windows: %LOCALAPPDATA%/Buzz/buzz.exe）。"""
    found = shutil.which("buzz")
    if found:
        return found
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Buzz" / "buzz.exe")
        candidates.append(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Buzz" / "buzz.exe")
    else:
        candidates += [
            Path("/Applications/Buzz.app/Contents/MacOS/buzz"),
            Path("/usr/local/bin/buzz"),
            Path("/opt/buzz/buzz"),
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _detect_desktop_relay() -> str | None:
    """从 buzz 桌面端配置里找它实际用的 relay（本地 localhost 或云端 wss），供 buzz-cli 复用。"""
    import re
    paths: list[Path] = []
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "")) / "xyz.block.buzz.app" / "agents"
        paths += [base / "managed-agents.json", base / "global-agent-config.json"]
    for p in paths:
        try:
            urls = re.findall(r"wss?://[a-zA-Z0-9._:\-/]+", p.read_text(encoding="utf-8", errors="ignore"))
            if urls:
                return urls[0]
        except Exception:
            continue
    return None


def _try_draft_create(display_name: str, agent_file: Path, channel: str | None, relay_url: str | None = None, lang: str = "zh") -> list[str]:
    """高级直连：buzz-cli 在 relay 上建号。缺任一配置即友好跳过，不报错。"""
    if not channel:
        return [_t(lang, "draft_no_channel")]
    buzz = _find_buzz_cli()
    if not buzz:
        return [_t(lang, "draft_no_cli")]
    if not os.environ.get("BUZZ_PRIVATE_KEY"):
        return [_t(lang, "draft_no_key")]
    cmd = [buzz]
    if relay_url:
        cmd += ["--relay", relay_url]  # buzz-cli 全局参数
    cmd += ["agents", "draft-create",
            "--channel", channel,
            "--display-name", display_name,
            "--system-prompt", "-"]  # 指令走 stdin
    try:
        r = subprocess.run(cmd, input=_system_prompt_of(agent_file).encode("utf-8"),
                           capture_output=True, timeout=60)
        if r.returncode == 0:
            return [_t(lang, "draft_ok_fmt", name=display_name, channel=channel)]
        err = (r.stderr or r.stdout).decode("utf-8", "replace").strip()[:200]
        return [_t(lang, "draft_fail_fmt", code=r.returncode, err=err)]
    except Exception as e:
        return [_t(lang, "draft_call_fail_fmt", err=e)]


def _load_buzz_config(config_path: str = ".alchemy-hive/config.toml") -> dict:
    """读配置里的 [buzz] 段：channel / relay_url（buzz-import 的自动直连参数）。"""
    from ..core.distill import load_config
    buzz = (load_config(config_path) or {}).get("buzz") or {}
    return {
        "channel": (buzz.get("channel") or "").strip() or None,
        "relay_url": (buzz.get("relay_url") or "").strip() or None,
    }


def _toml_str(value: str) -> str:
    """TOML basic string 转义：用户输入（channel/relay）含引号/反斜杠时不写坏配置。"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _save_buzz_channel(config_path: str, channel: str, relay_url: str | None = None) -> None:
    """把 [buzz] channel（+可选 relay_url）写进配置文件（文本级替换 [buzz] 段）。

    安全策略：只替换从 [buzz] 行开始、到下一个 [section] 或 EOF 之间的内容，
    不触及其他段；追加的 [buzz] 段总是写在文件末尾。
    """
    p = Path(config_path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    out: list[str] = []
    in_buzz = False
    for ln in text.splitlines():
        stripped = ln.strip()
        # 精确匹配段头（行首 [buzz] + 可选空白/注释），不匹配含 [buzz] 的值
        if stripped.startswith("[buzz]") and (len(stripped) == 6 or stripped[6] in (" ", "\t", "#", "]")):
            in_buzz = True
            continue
        if in_buzz:
            if stripped.startswith("[") and not stripped.startswith("[buzz"):
                in_buzz = False
                out.append(ln)
            continue
        out.append(ln)
    out.append("")
    out.append("[buzz]")
    out.append(f"channel = {_toml_str(channel)}")
    if relay_url:
        out.append(f"relay_url = {_toml_str(relay_url)}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def import_to_buzz(name: str = "", workdir: str = "build", channel: str | None = None, relay_url: str | None = None, lang: str = "zh") -> list[str]:
    """一键导入到 buzz：自动解析成品 → 打开文件夹 + 复制路径 → 可选 buzz-cli 直连建号。

    name 为空或找不到时，自动导入 build/export/ 下全部 .agent.json（高容错，适配社群场景）。
    任何"用户可犯的错"都返回易懂提示，不抛异常。
    """
    logs: list[str] = []
    export_dir = Path(workdir) / "export"

    # 1. 解析要导入的成品
    if not export_dir.exists():
        return [_t(lang, "no_build_1"), _t(lang, "no_build_2")]
    all_files = _list_exports(export_dir)
    if not all_files:
        return [_t(lang, "no_export_1"), _t(lang, "no_export_2")]

    exact = export_dir / f"{safe_filename(name)}.agent.json" if name else None
    if exact and exact.exists():
        targets = [exact]
    elif name:
        logs.append(_t(lang, "not_found_fmt", name=name, n=len(all_files)))
        logs.append(_t(lang, "not_found_hint"))
        targets = all_files
    else:
        logs.append(_t(lang, "all_imported_fmt", n=len(all_files)))
        targets = all_files

    # 2. 打开文件夹（一次）+ 复制路径
    if _open_folder(export_dir):
        logs.append(_t(lang, "opened_fmt", dir=export_dir))
    else:
        logs.append(_t(lang, "open_fail_fmt", dir=export_dir))
    if _copy_to_clipboard("\n".join(str(f.resolve()) for f in targets)):
        logs.append(_t(lang, "copied_fmt", n=len(targets)))
    else:
        logs.append(_t(lang, "copy_fail"))

    # 3. 导入引导 + 社群说明
    logs.append(_t(lang, "guide_import"))
    logs.append(_t(lang, "guide_count_fmt", n=len(targets)))

    # 4. 可选 buzz-cli 直连建号
    for t in targets:
        logs.extend(_try_draft_create(_display_name(t), t, channel, relay_url, lang=lang))
    return logs


def buzz_setup(config_path: str = ".alchemy-hive/config.toml", channel: str | None = None,
               relay_url: str | None = None) -> list[str]:
    """开发者引导：检查 buzz-cli / 密钥 / relay，配置直连建号，并把 channel 存进 [buzz] 配置。

    每一步缺失都给"傻瓜也能照做"的指引；全部就绪后可 `alchemy-hive buzz-import` 免填直连。
    """
    lines: list[str] = []
    buzz = _find_buzz_cli()
    if not buzz:
        return [
            "✗ 未找到 buzz-cli（命令行 `buzz`）。",
            "  安装（需 Rust 工具链）：cd <buzz 源码目录>/crates/buzz-cli && cargo install --path .",
            "  或去 https://github.com/block/buzz 的 Releases 下载 buzz-cli 预编译二进制。",
            "  装好后重新运行：alchemy-hive buzz-setup",
        ]
    lines.append(f"✓ buzz-cli：{buzz}")

    if not relay_url:
        relay_url = _detect_desktop_relay()
    if relay_url:
        lines.append(f"✓ 检测到桌面端 relay：{relay_url}")

    if not os.environ.get("BUZZ_PRIVATE_KEY"):
        hint = (
            f"  桌面端身份私钥存于系统钥匙串，无法被 buzz-cli 读取；要直连建号需额外设置一把："
            f"生成（nostr-tool generate / nostril）→ set BUZZ_PRIVATE_KEY=nsec1..."
        )
        return lines + [
            "✗ 未设置 BUZZ_PRIVATE_KEY（Nostr 私钥，nsec1... 或 64 位 hex），buzz-cli 用它当身份。",
            hint,
            "  注意：用独立身份建号后，agent 属于该身份，桌面端能否看到取决于它是否使用同一身份；",
            "  若只想把文件弄进桌面端，直接用「打开文件夹+复制路径」主路径即可。",
        ]
    lines.append("✓ BUZZ_PRIVATE_KEY：已设置")

    base = [buzz] + (["--relay", relay_url] if relay_url else [])
    try:
        r = subprocess.run(base + ["channels", "list"], capture_output=True, text=True, timeout=25)
    except Exception as e:
        return lines + [f"✗ 调用 buzz channels list 失败：{e}", "  请确认 buzz 桌面端/relay 正在运行。"]
    if r.returncode != 0:
        return lines + [
            f"✗ 连接 relay 失败（exit {r.returncode}）：{(r.stderr or r.stdout).strip()[:200]}",
            f"  检测到的 relay 是 {relay_url or 'http://localhost:3000'}；可用 --relay 或 BUZZ_RELAY_URL 覆盖。",
        ]
    try:
        data = _json.loads(r.stdout)
        channels = data if isinstance(data, list) else data.get("channels", data.get("data", []))
        lines.append(f"✓ relay 连通，检测到 {len(channels)} 个频道：")
        for c in channels[:20]:
            cid = c.get("id") or c.get("channel_id") or c.get("uuid") or "?"
            cname = c.get("name") or c.get("title") or cid
            lines.append(f"    - {cname}  ({cid})")
    except Exception:
        lines.append("✓ relay 连通，频道列表：")
        lines.append("    " + (r.stdout or "").strip()[:400])

    if channel:
        _save_buzz_channel(config_path, channel, relay_url)
        lines.append(f"✓ 已把 channel={channel} 存进 {config_path} 的 [buzz] 段，之后 buzz-import 免填直连。")
    else:
        lines.append("下一步：记下要用的频道 UUID，然后：")
        lines.append("  alchemy-hive buzz-import --name 人物名 --channel <UUID>   # 单次直连")
        lines.append("  alchemy-hive buzz-setup --channel <UUID>                # 存进配置，之后免填")
    return lines
