"""Alchemy Hive 桌面界面（pywebview 新拟物派 Neumorphism）。

浅灰同色系 + 双重阴影（右下暗 / 左上亮）模拟光源：凸起=可交互，凹陷=输入区/激活。
Python 端只做 js_api 桥接，业务逻辑复用 actions.run_pipeline。

面向低门槛用户的傻瓜化处理：
- 聊天文件支持拖拽上传 + 即时格式识别（平台/消息数）
- 模型供应商下拉选择，自动映射 base_url 并自动匹配默认模型名，也可自定义
- 中/英双语界面：启动自动检测系统语言，界面右上角可随时切换
"""
import base64
import json
import os
import threading
import time
import uuid
from pathlib import Path

import webview

from .actions import run_pipeline
from ..core.parser import parse_messages, detect_source, SOURCE_LABELS
from ..core.safe import safe_filename
from ..core.distill import load_config, resolve_config_path
from ..buzz.importing import import_to_buzz

# 模块级窗口引用：绝不能挂在 js_api 实例上。pywebview 会用 dir()/getattr() 递归枚举
# js_api 的整个对象图来生成 JS 桥接函数表，把 Window 挂在实例上会把递归拖入
# window.native 的 .NET/COM 无障碍对象图 → RecursionError → 窗口无法加载。
_GUI_WINDOW = None


def _gui_workdir() -> Path:
    """GUI 工作目录固定在用户主目录下：无论从哪个目录/快捷方式启动，
    产物与拖拽落盘都在同一处，不随 CWD 漂移（CLI 仍默认用 CWD 的 build/）。"""
    return Path.home() / ".alchemy-hive" / "build"


# 窗口标题（按语言）：启动与运行时切语言共用
_GUI_TITLES = {
    "zh": "Alchemy Hive · 把微信聊天蒸馏成 AI 朋友",
    "en": "Alchemy Hive · Distill chats into AI friends",
}

# 英文界面：静态 HTML 文案的整句替换表（中文模板保持不变，仅 en 构建时应用）
_EN_HTML = {
    "<html lang=\"zh-CN\">": "<html lang=\"en\">",
    "任意聊天源 → AI persona → 任意 agent 平台":
        "Any chat source → AI persona → Any agent platform",
    "本项目完全开源，不会获取您的任何个人信息和 API key。":
        "Open source — we never collect your personal data or API keys.",
    "原料导入 · 选导出平台（自动识别也行），把聊天文件拖进来":
        "Step 1 · Choose a platform (auto-detect works), then drop your chat file",
    "蒸馏人物 · 性格画像与模型（画像越具体越像 TA）":
        "Step 2 · Persona & model (the more specific the profile, the closer it gets)",
    "导入buzz · 把 AI 朋友装进 buzz 开聊（buzz 是免费开源 AI 聊天室，可组建无数个社群）":
        "Import to buzz · put your AI friend into buzz (free & open source — build any number of communities)",
    "选择来源": "Source",
    "蒸馏": "Distill",
    "成品文件": "Export",
    "导入buzz": "Into buzz",
    "自动识别（推荐）": "Auto-detect (Recommended)",
    "微信（WeFlow 导出）": "WeChat (via WeFlow)",
    "微信 txt": "WeChat txt",
    "其他（通用字段解析）": "Other (generic)",
    "把聊天文件拖到这里（微信 / Telegram / WhatsApp / Instagram / Facebook / Discord / Slack / iMessage / QQ 导出）":
        "Drop your chat file here (WeChat / Telegram / WhatsApp / Instagram / Facebook / Discord / Slack / iMessage / QQ export)",
    "浏览文件…": "Browse…",
    "Ta 的名称（如：小明）": "Their name (e.g. Xiaoming)",
    "你的昵称（可选）：对话里你的名字，用于区分方向（如：我 / 张三）":
        "Your nickname (optional): your name in this chat, to tell who is you",
    "性格画像（可选，最高优先级）如：INTJ 摩羯座 爱吐槽 重感情":
        "Personality profile (optional, highest priority) e.g. INTJ Capricorn sarcastic loyal",
    "纠正（可选）：对上次蒸馏不满意时填，如：他不会冷淡，他其实很细心":
        "Correction (optional): if the last result felt off, e.g. he's not cold — he's actually attentive",
    "自定义模型（手动填写地址和模型名）": "Custom model (fill in URL and model name)",
    "DeepSeek（深度求索）": "DeepSeek",
    "通义千问（阿里云）": "Qwen (Alibaba)",
    "Kimi（月之暗面）": "Kimi (Moonshot)",
    "智谱 GLM": "Zhipu GLM",
    "豆包（火山方舟）": "Doubao (Volcano)",
    "腾讯混元": "Tencent Hunyuan",
    "SiliconFlow（硅基流动）": "SiliconFlow",
    "本地 Ollama": "Local Ollama",
    "本地 vLLM": "Local vLLM",
    "模型地址 base_url（选供应商后自动填入，可再修改）":
        "Model URL base_url (auto-filled when you pick a provider, editable)",
    "模型名（自动匹配，可再修改）": "Model name (auto-matched, editable)",
    "API key（向模型供应商申请，必需）": "API key (required — get it from your provider)",
    "本项目完全开源，不会获取您的任何个人信息和 key；API key 仅用于调用您自己选择的模型服务，只保存在本地。":
        "Open source — your key only calls the model service you chose and stays on this device.",
    "选择供应商后会自动填好地址和模型名；想用别的模型直接改这两格即可。API key 请去对应供应商官网申请。性格画像填得越具体，蒸馏出来越像 TA（如：INTJ 摩羯座 爱吐槽 重感情 游戏宅）。":
        "Picking a provider auto-fills the URL and model name — you can edit them. Get an API key from your provider's site. The more specific the profile, the closer the result.",
    "导出共同记忆（明文、含真实内容，默认不含）":
        "Export shared memories (plaintext, contains real content — off by default)",
    "开始蒸馏": "Start distillation",
    "已生成 <span id=\"success_path\"></span> —— 往下拉到「导出」选择格式，或直接开始聊天测试。":
        "Generated <span id=\"success_path\"></span> — choose an export format below, or start chatting.",
    "蒸馏成功 ✓": "Distillation complete ✓",
    "已生成 <span id=\"success_path\"></span> —— 往下拉到「导入buzz」卡片，一键装进 buzz。":
        "Generated <span id=\"success_path\"></span> — scroll to “Import to buzz” and you're done.",
    "运行结果 · 日志": "Run log",
    "运行后在这里查看步骤日志…": "Steps will appear here as you run…",
    "点下面的按钮 —— 自动打开导出文件夹并复制路径；<b>名称栏不填也会全部导入</b>":
        "Click below — it opens the export folder and copies the paths; <b>no name needed, imports everything</b>",
    "打开 buzz 桌面端 → 进 My Agents → 点「导入」→ 粘贴路径（或直接把文件拖进窗口）":
        "Open the buzz desktop app → My Agents → Import → paste the path (or drag the file in)",
    "在频道里 <b>@这个 agent</b> 就能聊天；把多个 agent 拉进同一频道就是一个社群，想建几个建几个":
        "Mention <b>@this agent</b> in a channel to chat; drop several into one channel and you've built a community.",
    "导入到 buzz · 打开文件夹并复制路径": "Import to buzz · open folder & copy path",
    "开发者进阶：想跳过手动导入、让 buzz-cli 直连 relay 自动建号？终端运行 <code>alchemy-hive buzz-setup</code> 完成配置，之后 <code>buzz-import</code> 免填直连。":
        "Developers: skip manual import and let buzz-cli create agents via relay? Run <code>alchemy-hive buzz-setup</code>, then <code>buzz-import</code> works directly.",
    # 供应商 JS 标签（PROVIDERS 对象里的裸名，非显示用，仅保持英文构建干净）
    "通义千问": "Qwen",
    "豆包": "Doubao",
    "腾讯混元": "Tencent Hunyuan",
    # API key 明文切换按钮（静态初值；运行时由 JS 按 T.show_key/hide_key 更新）
    "显示": "Show",
    # 新增卡片文案
    "导出": "Export",
    "测试": "Test",
    "质量评分": "Quality Score",
    "点击下方按钮自动评分": "Click below to auto-evaluate",
    "自动评分": "Auto-evaluate",
    "发送": "Send",
    "说点什么": "Say something",
    "导入 buzz（可选，点击展开）": "Import to buzz (optional, click to expand)",
    # 新增卡片文案（export/chat/evaluate）
    "导出 · 选择目标平台格式": "Export · Choose target format",
    "全部格式": "All formats",
    "System Prompt (.txt) — 通用": "System Prompt (.txt) — Universal",
    "可粘贴到 Claude Projects / OpenAI GPTs 的 system prompt 字段":
        "Can be pasted into Claude Projects / OpenAI GPTs system prompt field",
    "聊天测试 · 直接和蒸馏出的 persona 对话": "Chat · Talk to the distilled persona directly",
    "说点什么...": "Say something...",
    "发送": "Send",
    "质量评分": "Quality Score",
    "点击下方按钮自动评分": "Click below to auto-evaluate",
    "自动评分": "Auto-evaluate",
    "蒸馏完成后在这里和 TA 聊天...": "Start chatting after distillation...",
    "导出失败": "Export failed",
    "聊天测试 · 直接和蒸馏出的 persona 对话": "Chat · Talk to the distilled persona directly",
}

# JS 运行时文案（动态消息，需按语言拼接/占位）
_T = {
    "zh": {
        "self_required": "你的昵称（必填）：该平台导出不带方向，需要它区分谁是你",
        "self_optional": "你的昵称（可选）：对话里你的名字，用于区分方向（如：我 / 张三）",
        "selected": "已选择：",
        "no_file": "没有拿到文件，请改用「浏览文件」选择。",
        "detecting": "正在识别文件格式…",
        "detected": "已识别：{format} · {count} 条消息",
        "failed_detect": "无法识别：{error}",
        "fill_first": "请先填写：{missing}。",
        "fields": "聊天文件|Ta 的名称|模型地址|API key|模型名",
        "sep": "、",
        "distilling": "正在蒸馏中…",
        "start": "开始蒸馏",
        "done": "完成 已生成 {path}，点击「导入到 buzz」即可。",
        "error_prefix": "错误: ",
        "export_re": "已生成 (?:-> )?(.+)",
        "warn_marker": "提醒",
        "show_key": "显示",
        "hide_key": "隐藏",
    },
    "en": {
        "self_required": "Your nickname (required): this export has no direction — needed to tell who is you",
        "self_optional": "Your nickname (optional): your name in this chat, to tell who is you",
        "selected": "Selected: ",
        "no_file": "No file received — use “Browse” instead.",
        "detecting": "Detecting file format…",
        "detected": "Detected: {format} · {count} messages",
        "failed_detect": "Couldn't read: {error}",
        "fill_first": "Please fill in: {missing}.",
        "fields": "chat file|person's name|model URL|API key|model name",
        "sep": ", ",
        "distilling": "Distilling…",
        "start": "Start distillation",
        "done": "Done — generated {path}. Click “Import to buzz” to proceed.",
        "error_prefix": "Error: ",
        "export_re": "Generated (?:-> )?(.+)",
        "warn_marker": "Reminder",
        "show_key": "Show",
        "hide_key": "Hide",
    },
}

# 常见后端错误的中→英片段（GUI 边界尽力翻译；未覆盖的保留原文）
_EN_ERRORS = {
    "文件不存在": "File not found",
    "不支持的文件类型": "Unsupported file type",
    "无法识别的 WeFlow JSON 结构": "Unrecognized JSON structure",
    "解析出 0 条消息": "Parsed 0 messages",
    "未识别为微信导出的 txt": "Unrecognized text export format",
    "未配置模型 API key": "No model API key configured",
    "LLM 蒸馏失败": "LLM distillation failed",
    "模型请求超时": "Model request timed out",
    "无法连接模型服务": "Cannot reach model service",
}


def _tr_error(text: str, lang: str) -> str:
    if lang != "en":
        return text
    for zh, en in _EN_ERRORS.items():
        text = text.replace(zh, en)
    return text


def _detect_lang() -> str:
    """按系统 locale 猜界面语言：中文系统 → zh，其他 → en。"""
    import locale
    try:
        # getdefaultlocale() 在 Python 3.11 废弃、3.15 删除；优先用 getlocale()
        _get = getattr(locale, "getlocale", None)
        code = (_get() or ("", ""))[0] if _get else ""
        if not code:
            code = (locale.getdefaultlocale() or ("", ""))[0] or ""
    except Exception:
        code = os.environ.get("LANG", "")
    return "zh" if code.lower().startswith("zh") else "en"


def _build_html(lang: str, state_json: str = "") -> str:
    """按语言构建界面 HTML。中文直接用原始模板；英文做整句替换 + 注入 JS 文案。

    替换按 key 长度降序执行：避免「导入buzz」这类短词先被替换、破坏含它的整句匹配。
    state_json：切语言前 JS 采集的表单状态（合法 JSON 对象才注入，页面加载后恢复）。
    """
    html = _HTML
    if lang == "en":
        for zh in sorted(_EN_HTML, key=len, reverse=True):
            html = html.replace(zh, _EN_HTML[zh])
    t = json.dumps(_T.get(lang, _T["zh"]), ensure_ascii=False)
    html = html.replace("/*__T__*/", f"window.T = {t};")
    state = "null"
    if state_json.startswith("{"):
        try:
            json.loads(state_json)  # 非法 JSON 不注入，避免拼出坏 JS
            state = state_json
        except Exception:
            pass
    html = html.replace("/*__STATE__*/", f"window.__S = {state};")
    html = html.replace("__ZH_SEL__", " selected" if lang == "zh" else "")
    html = html.replace("__EN_SEL__", " selected" if lang == "en" else "")
    html = html.replace("__LANG_LABEL__", "语言" if lang == "zh" else "Language")
    return html

_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Alchemy Hive</title>
<style>
  :root {
    --bg-body: #d6dbe3;       /* 页面背景（略深，衬托卡片凸起） */
    --bg-elem: #e5e9f0;       /* 卡片/按钮/输入统一浅灰 */
    --dark: #a6aeb8;          /* 暗阴影（右下，更明显） */
    --light: #ffffff;         /* 亮阴影（左上） */
    --text: #2b3038;          /* 主文字（更深，保证对比） */
    --muted: #5b6472;         /* 次要文字 */
    --placeholder: #8b93a1;   /* 占位灰 */
    --accent: #3f6fe0;        /* 主操作强调色 */
    --ok: #2e9e57;            /* 成功 */
    --warn: #c07c1f;          /* 提醒 */
    --err: #d64545;           /* 错误 */
    --radius-card: 18px;
    --radius-ctl: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    /* 英文走 Segoe UI/Helvetica；中文回退到宋体系（思源宋体 → 华文宋体 → 宋体/新宋体） */
    font-family: "Segoe UI", "Helvetica Neue", Arial, "Songti SC", "STSong", "Noto Serif SC", "Source Han Serif SC", "SimSun", "NSimSun", serif;
    background: var(--bg-body);
    color: var(--text);
    min-height: 100vh;
    padding: 28px 32px 32px;
    user-select: none;
  }

  /* 品牌 */
  .brand { margin-bottom: 8px; }
  .brand h1 { font-size: 24px; font-weight: 700; color: #1f2733; letter-spacing: .5px; }
  .brand p { color: var(--muted); font-size: 12px; margin-top: 4px; }
  .privacy-note { color: var(--ok); font-size: 11.5px; }
  .key-note { font-size: 11px; color: var(--warn); margin-top: 6px; line-height: 1.6; }

  /* 语言切换：右上角固定，显眼 */
  .lang-switch {
    position: fixed;
    top: 16px;
    right: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    z-index: 50;
  }
  .lang-switch label { font-size: 11.5px; color: var(--muted); font-weight: 600; }
  .lang-switch select {
    background: var(--bg-elem);
    border: none;
    border-radius: 10px;
    box-shadow: inset 3px 3px 6px var(--dark), inset -3px -3px 6px var(--light);
    padding: 7px 10px;
    color: var(--text);
    font-size: 12px;
    cursor: pointer;
  }

  /* 导入buzz 指南 */
  .guide-step { display: flex; gap: 10px; align-items: flex-start; font-size: 12.5px; color: var(--text); line-height: 1.7; margin-bottom: 9px; }
  .gs-num { flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-top: 2px; }
  .buzz-btn {
    width: 100%; padding: 14px; margin-top: 14px; border: none; border-radius: var(--radius-ctl);
    background: linear-gradient(135deg, #2e9e57, #258549); color: #fff;
    font-size: 15px; font-weight: 700; letter-spacing: 2px; cursor: pointer;
    box-shadow: 6px 6px 12px var(--dark), -6px -6px 12px var(--light); transition: all .2s;
  }
  .buzz-btn:hover { filter: brightness(1.06); }
  .buzz-btn:active { box-shadow: inset 4px 4px 8px rgba(0,0,0,.3); }
  .dev-note { margin-top: 12px; font-size: 11px; color: var(--placeholder); line-height: 1.6; }
  .dev-note code { background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 4px; font-family: Consolas, "Microsoft YaHei UI", monospace; }

  /* 四步进度条：序号圆点 + 连接线，完成变绿打勾 */
  .steps { display: flex; align-items: center; justify-content: center; margin: 20px 0 18px; }
  .step { display: flex; flex-direction: column; align-items: center; gap: 7px; }
  .dot {
    width: 32px; height: 32px; border-radius: 50%;
    background: var(--bg-elem); color: var(--muted);
    font-size: 14px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 5px 5px 10px var(--dark), -5px -5px 10px var(--light);
    transition: all .25s;
  }
  .dot .check { display: none; }
  .step-label { font-size: 12px; color: var(--muted); font-weight: 600; transition: color .25s; }
  .step.active .dot { background: var(--accent); color: #fff; box-shadow: inset 3px 3px 6px rgba(0,0,0,.25); }
  .step.active .step-label { color: var(--accent); }
  .step.done .dot { background: var(--ok); color: #fff; }
  .step.done .dot .num { display: none; }
  .step.done .dot .check { display: inline; }
  .step.done .step-label { color: var(--ok); }
  .step-sep { width: 34px; height: 3px; border-radius: 2px; background: var(--dark); opacity: .22; margin: 0 12px; transform: translateY(-9px); }

  /* 卡片：凸起 + 入场淡入 */
  .card {
    background: var(--bg-elem);
    border-radius: var(--radius-card);
    box-shadow: 10px 10px 20px var(--dark), -10px -10px 20px var(--light);
    padding: 20px 22px;
    margin-bottom: 18px;
    animation: fadeUp .45s ease both;
  }
  .card:nth-of-type(2) { animation-delay: .06s; }
  .card:nth-of-type(3) { animation-delay: .12s; }
  .log-wrap { animation: fadeUp .45s ease .1s both; }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
  .card .label { font-size: 12px; color: var(--muted); margin-bottom: 12px; font-weight: 600; }
  .lb-num { display: inline-flex; align-items: center; justify-content: center; width: 19px; height: 19px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 11px; font-weight: 700; margin-right: 8px; vertical-align: 1px; }
  .row { display: flex; gap: 10px; }
  .key-row { display: flex; gap: 10px; }
  .key-toggle { flex-shrink: 0; padding: 0 14px; font-size: 12px; color: var(--muted); letter-spacing: 1px; }

  /* 输入框/下拉：凹陷，文字清晰 */
  .field {
    flex: 1; width: 100%;
    background: var(--bg-elem);
    border: none;
    border-radius: var(--radius-ctl);
    box-shadow: inset 5px 5px 10px var(--dark), inset -5px -5px 10px var(--light);
    padding: 12px 15px;
    color: var(--text);
    font-size: 13.5px;
    transition: box-shadow .2s;
  }
  .field:focus {
    box-shadow: inset 7px 7px 14px var(--dark), inset -7px -7px 14px var(--light);
    outline: none;
  }
  .field::placeholder { color: var(--placeholder); }
  select.field { appearance: auto; cursor: pointer; }
  .spacer { height: 14px; }
  .hint { font-size: 11px; color: var(--placeholder); margin-top: 8px; line-height: 1.6; }

  /* 拖拽上传区：虚线框 + 悬停高亮 */
  .dropzone {
    border: 2px dashed #a9b3c2;
    border-radius: var(--radius-ctl);
    padding: 18px 16px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    transition: border-color .2s, background .2s;
  }
  .dropzone.over { border-color: var(--accent); background: rgba(63,111,224,.08); color: var(--accent); }
  .file-status { font-size: 12px; margin-top: 8px; }
  .file-status.ok { color: var(--ok); }
  .file-status.warn { color: var(--warn); }
  .file-status.err { color: var(--err); }

  /* 幽灵按钮（浏览） */
  .ghost {
    background: var(--bg-elem);
    border: none;
    border-radius: var(--radius-ctl);
    box-shadow: 6px 6px 12px var(--dark), -6px -6px 12px var(--light);
    padding: 0 20px;
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: box-shadow .2s;
  }
  .ghost:hover { box-shadow: 4px 4px 8px var(--dark), -4px -4px 8px var(--light); }
  .ghost:active { box-shadow: inset 4px 4px 8px var(--dark), inset -4px -4px 8px var(--light); color: #2c4fb0; }

  /* 主按钮：大号突出 */
  .primary {
    width: 100%;
    margin: 4px 0 20px;
    padding: 16px;
    border: none;
    border-radius: var(--radius-ctl);
    background: var(--accent);
    color: #fff;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 3px;
    cursor: pointer;
    box-shadow: 8px 8px 16px #9aa3af, -8px -8px 16px #ffffff;
    transition: box-shadow .2s;
  }
  .primary:hover { box-shadow: 5px 5px 10px #9aa3af, -5px -5px 10px #ffffff; }
  .primary:active { box-shadow: inset 5px 5px 10px rgba(0,0,0,0.28), inset -5px -5px 10px rgba(255,255,255,0.32); }
  .primary:disabled { opacity: .6; cursor: not-allowed; }
  .spinner {
    display: inline-block; width: 15px; height: 15px;
    border: 2px solid rgba(255,255,255,.35); border-top-color: #fff;
    border-radius: 50%; vertical-align: middle; margin-right: 8px;
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .hidden { display: none; }

  /* 成功横幅 + 完成态步骤（绿） + 导入按钮脉冲 */
  .success-banner {
    display: none;
    background: linear-gradient(135deg, #2e9e57, #258549);
    color: #fff;
    border-radius: var(--radius-card);
    padding: 14px 18px;
    margin-bottom: 14px;
    font-size: 13px;
    line-height: 1.7;
    box-shadow: 8px 8px 16px #9aa3af, -8px -8px 16px #ffffff;
  }
  .success-banner.show { display: block; }
  .success-banner b { font-size: 14px; letter-spacing: 1px; }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(46,158,87,.5); }
    70% { box-shadow: 0 0 0 14px rgba(46,158,87,0); }
    100% { box-shadow: 0 0 0 0 rgba(46,158,87,0); }
  }
  .btn-pulse { animation: pulse 1.1s 2; }

  /* 日志：突出显示面板（凹陷 + 大字号 + 深字）；内容可选中复制 */
  .log-wrap { margin-top: 2px; }
  .log-label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
  .log {
    background: var(--bg-elem);
    border-radius: var(--radius-card);
    box-shadow: inset 8px 8px 16px var(--dark), inset -8px -8px 16px var(--light);
    padding: 16px 20px;
    min-height: 190px;
    max-height: 300px;
    overflow-y: auto;
    font-size: 13px;
    line-height: 1.9;
    font-family: Consolas, "Microsoft YaHei UI", monospace;
    user-select: text;
    cursor: text;
  }
  .log::-webkit-scrollbar { width: 8px; }
  .log::-webkit-scrollbar-thumb { background: var(--dark); border-radius: 4px; }
  .log::-webkit-scrollbar-track { background: transparent; }
  .log .info { color: var(--accent); }
  .log .ok { color: var(--ok); }
  .log .warn { color: var(--warn); }
  .log .err { color: var(--err); }
  .log .plain { color: var(--text); }
  .log .empty { color: var(--placeholder); }
</style>
</head>
<body>
  <div class="lang-switch">
    <label for="lang_sel">__LANG_LABEL__</label>
    <select id="lang_sel" onchange="onLang(this.value)">
      <option value="zh"__ZH_SEL__>中文</option>
      <option value="en"__EN_SEL__>English</option>
    </select>
  </div>

  <div class="brand">
    <h1>Alchemy Hive</h1>
    <p>任意聊天源 → AI persona → 任意 agent 平台</p>
    <p class="privacy-note">本项目完全开源，不会获取您的任何个人信息和 API key。</p>
  </div>

  <div class="steps">
    <div class="step active" id="s1"><div class="dot"><span class="num">1</span><span class="check">✓</span></div><div class="step-label">选择来源</div></div>
    <div class="step-sep"></div>
    <div class="step" id="s2"><div class="dot"><span class="num">2</span><span class="check">✓</span></div><div class="step-label">蒸馏</div></div>
    <div class="step-sep"></div>
    <div class="step" id="s3"><div class="dot"><span class="num">3</span><span class="check">✓</span></div><div class="step-label">导出 / 测试</div></div>
  </div>

  <div class="card">
    <div class="label"><span class="lb-num">1</span>原料导入 · 选导出平台（自动识别也行），把聊天文件拖进来</div>
    <select class="field" id="source" style="margin-bottom:12px;" onchange="onSource()">
      <option value="auto" selected>自动识别（推荐）</option>
      <optgroup label="常用">
        <option value="weflow">微信（WeFlow 导出）</option>
        <option value="wechat">微信 txt</option>
        <option value="telegram">Telegram</option>
        <option value="whatsapp">WhatsApp</option>
        <option value="discord">Discord</option>
      </optgroup>
      <optgroup label="其他">
        <option value="slack">Slack</option>
        <option value="imessage">iMessage</option>
        <option value="qq">QQ</option>
        <option value="meta">Instagram / Facebook</option>
        <option value="generic">其他（通用字段解析）</option>
      </optgroup>
    </select>
    <div class="dropzone" id="dropzone"
         ondragover="onDragOver(event)" ondragleave="onDragLeave(event)" ondrop="onDrop(event)">
      <div id="drop_hint">把聊天文件拖到这里（微信 / Telegram / WhatsApp / Instagram / Facebook / Discord / Slack / iMessage / QQ 导出）</div>
      <div class="row" style="justify-content:center; margin-top:12px;">
        <button class="ghost" onclick="pick()">浏览文件…</button>
      </div>
    </div>
    <input type="hidden" id="chat">
    <div class="file-status" id="file_status"></div>
  </div>

  <div class="card">
    <div class="label"><span class="lb-num">2</span>蒸馏人物 · 性格画像与模型（画像越具体越像 TA）</div>
    <input class="field" id="name" placeholder="Ta 的名称（如：小明）">
    <div class="spacer"></div>
    <input class="field" id="self_name" placeholder="你的昵称（可选）：对话里你的名字，用于区分方向（如：我 / 张三）">
    <div class="spacer"></div>
    <input class="field" id="profile" placeholder="性格画像（可选，最高优先级）如：INTJ 摩羯座 爱吐槽 重感情">
    <div class="spacer"></div>
    <input class="field" id="fix" placeholder="纠正（可选）：对上次蒸馏不满意时填，如：他不会冷淡，他其实很细心">
    <div class="spacer"></div>
    <select class="field" id="provider" onchange="onProvider()">
      <option value="custom" selected>自定义模型（手动填写地址和模型名）</option>
      <option value="deepseek">DeepSeek（深度求索）</option>
      <option value="openai">OpenAI</option>
      <option value="qwen">通义千问（阿里云）</option>
      <option value="kimi">Kimi（月之暗面）</option>
      <option value="zhipu">智谱 GLM</option>
      <option value="doubao">豆包（火山方舟）</option>
      <option value="hunyuan">腾讯混元</option>
      <option value="siliconflow">SiliconFlow（硅基流动）</option>
      <option value="ollama">本地 Ollama</option>
      <option value="vllm">本地 vLLM</option>
    </select>
    <div class="spacer"></div>
    <input class="field" id="base_url" placeholder="模型地址 base_url（选供应商后自动填入，可再修改）">
    <div class="spacer"></div>
    <input class="field" id="model" placeholder="模型名（自动匹配，可再修改）">
    <div class="spacer"></div>
    <div class="key-row">
      <input class="field" id="api_key" type="password" placeholder="API key（向模型供应商申请，必需）" style="flex:1">
      <button class="ghost key-toggle" id="key_toggle" type="button" onclick="toggleKey()">显示</button>
    </div>
    <div class="key-note">本项目完全开源，不会获取您的任何个人信息和 key；API key 仅用于调用您自己选择的模型服务，只保存在本地。</div>
    <div class="hint">选择供应商后会自动填好地址和模型名；想用别的模型直接改这两格即可。API key 请去对应供应商官网申请。性格画像填得越具体，蒸馏出来越像 TA（如：INTJ 摩羯座 爱吐槽 重感情 游戏宅）。</div>
    <div class="spacer"></div>
    <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);cursor:pointer;">
      <input type="checkbox" id="with_memory" style="accent-color:var(--accent);width:15px;height:15px;">
      导出共同记忆（明文、含真实内容，默认不含）
    </label>
  </div>

  <button class="primary" id="go" onclick="start()">
    <span class="spinner hidden" id="spinner"></span><span id="go_text">开始蒸馏</span>
  </button>

  <div class="success-banner" id="success_banner">
    <b>蒸馏成功 ✓</b><br>
    已生成 <span id="success_path"></span> —— 往下拉到「导出」选择格式，或直接开始聊天测试。
  </div>


  <!-- 导出卡片：多格式 + buzz 导入 -->
  <div class="card" id="export_card" style="display:none;">
    <div class="label"><span class="lb-num">3</span>导出 · 选择目标平台格式</div>
    <div class="row" style="margin-bottom:10px;">
      <select class="field" id="export_fmt" style="flex:2;">
        <option value="all">全部格式</option>
        <option value="text">System Prompt (.txt) — 通用</option>
        <option value="buzz">buzz (.agent.json)</option>
        <option value="sillytavern">SillyTavern (character_card_v2)</option>
      </select>
      <button class="ghost" onclick="exportPersona()" style="flex:1;">导出</button>
    </div>
    <div class="file-status" id="export_status"></div>
    <div class="guide-step" style="margin-top:12px; font-size:11.5px; color:var(--muted);">
      <span class="gs-num" style="font-size:10px;">💡</span>
      <span><b>.txt</b> 可粘贴到 Claude Projects / OpenAI GPTs 的 system prompt 字段</span>
    </div>
  </div>

  <!-- 聊天测试卡片 -->
  <div class="card" id="chat_card" style="display:none;">
    <div class="label"><span class="lb-num">4</span>聊天测试 · 直接和蒸馏出的 persona 对话</div>
    <div class="log" id="chat_msgs" style="min-height:120px; max-height:260px; margin-bottom:10px; user-select:text; cursor:text;">
      <span class="empty">蒸馏完成后在这里和 TA 聊天...</span>
    </div>
    <div class="row">
      <input class="field" id="chat_input" placeholder="说点什么..." style="flex:1;" onkeydown="if(event.key==='Enter')sendChat()">
      <button class="ghost" onclick="sendChat()" style="flex:0 0 auto; padding:0 18px;">发送</button>
    </div>
  </div>

  <!-- 自动评分卡片 -->
  <div class="card" id="eval_card" style="display:none;">
    <div class="label">质量评分</div>
    <div id="eval_content">
      <div class="row" style="align-items:center; gap:16px;">
        <div id="eval_score" style="font-size:36px; font-weight:700; color:var(--muted);">--</div>
        <div style="flex:1;">
          <div id="eval_summary" style="font-size:13px; color:var(--text);">点击下方按钮自动评分</div>
          <div id="eval_dims" style="font-size:11px; color:var(--muted); margin-top:4px;"></div>
        </div>
      </div>
      <button class="ghost" onclick="runEvaluate()" style="margin-top:10px; width:100%;">自动评分</button>
      <div id="eval_suggestions" style="font-size:11px; color:var(--placeholder); margin-top:8px;"></div>
    </div>
  </div>


  <div class="log-wrap">
    <div class="log-label">运行结果 · 日志</div>
    <div class="log" id="log">
      <span class="empty">运行后在这里查看步骤日志…</span>
    </div>
  </div>

  <div class="card" style="opacity:.7;">
    <div class="label" style="cursor:pointer;" onclick="var el=document.getElementById('buzz_detail');el.style.display=el.style.display==='none'?'block':'none';">导入 buzz（可选，点击展开）</div>
    <div id="buzz_detail" style="display:none;">
    <div class="guide-step"><span class="gs-num">1</span><span>点下面的按钮 —— 自动打开导出文件夹并复制路径；<b>名称栏不填也会全部导入</b></span></div>
    <div class="guide-step"><span class="gs-num">2</span><span>打开 buzz 桌面端 → 进 My Agents → 点「导入」→ 粘贴路径（或直接把文件拖进窗口）</span></div>
    <div class="guide-step"><span class="gs-num">3</span><span>在频道里 <b>@这个 agent</b> 就能聊天；把多个 agent 拉进同一频道就是一个社群，想建几个建几个</span></div>
    <button class="buzz-btn" id="buzz_btn" onclick="buzzImport()">导入到 buzz · 打开文件夹并复制路径</button>
    <div class="dev-note">开发者进阶：想跳过手动导入、让 buzz-cli 直连 relay 自动建号？终端运行 <code>alchemy-hive buzz-setup</code> 完成配置，之后 <code>buzz-import</code> 免填直连。</div>
    </div><!-- /buzz_detail -->
  </div>

<script>
  /*__T__*/
  /*__STATE__*/

  /* 切语言保留表单状态：切换前采集，重载后恢复（不再清空用户已填内容） */
  function collectState() {
    return JSON.stringify({
      chat: el("chat").value, name: el("name").value, self_name: el("self_name").value,
      profile: el("profile").value, fix: el("fix").value, provider: el("provider").value,
      base_url: el("base_url").value, model: el("model").value, api_key: el("api_key").value,
      source: el("source").value, with_memory: el("with_memory").checked
    });
  }
  function restoreState() {
    var s = window.__S;
    if (!s) return;
    try {
      if (s.source) el("source").value = s.source;
      if (s.provider) el("provider").value = s.provider;   // 直接赋值，不触发 onProvider（不覆盖已填地址/模型）
      el("name").value = s.name || "";
      el("self_name").value = s.self_name || "";
      el("profile").value = s.profile || "";
      el("fix").value = s.fix || "";
      el("base_url").value = s.base_url || "";
      el("model").value = s.model || "";
      el("api_key").value = s.api_key || "";
      el("with_memory").checked = !!s.with_memory;
      if (s.chat) {
        el("chat").value = s.chat;
        el("drop_hint").textContent = T.selected + s.chat;
        el("dropzone").style.borderColor = "var(--ok)";
      }
      onSource();   // 恢复昵称提示；已有文件时会自动重新识别
    } catch (e) {}
  }
  function onLang(v) { pywebview.api.set_lang(v, collectState()); }

  /* API key 明文/密文切换 */
  function toggleKey() {
    var k = el("api_key"), b = el("key_toggle");
    if (k.type === "password") { k.type = "text"; b.textContent = T.hide_key; }
    else { k.type = "password"; b.textContent = T.show_key; }
  }

  /* 2026-08 常见 OpenAI-compatible 供应商：选供应商自动映射 base_url 与默认模型名 */
  var PROVIDERS = {
    deepseek:      {label:"DeepSeek",      base_url:"https://api.deepseek.com/v1",                    model:"deepseek-v4-flash"},
    openai:        {label:"OpenAI",        base_url:"https://api.openai.com/v1",                      model:"gpt-5.5"},
    qwen:          {label:"通义千问",       base_url:"https://dashscope.aliyuncs.com/compatible-mode/v1", model:"qwen3.7-plus"},
    kimi:          {label:"Kimi",          base_url:"https://api.moonshot.cn/v1",                     model:"kimi-k3"},
    zhipu:         {label:"智谱 GLM",       base_url:"https://open.bigmodel.cn/api/paas/v4",           model:"glm-5.2"},
    doubao:        {label:"豆包",           base_url:"https://ark.cn-beijing.volces.com/api/v3",       model:"doubao-seed-1.6"},
    hunyuan:       {label:"腾讯混元",       base_url:"https://api.hunyuan.cloud.tencent.com/v1",       model:"hunyuan-turbos-latest"},
    siliconflow:   {label:"SiliconFlow",   base_url:"https://api.siliconflow.cn/v1",                  model:"Qwen/Qwen3-32B"},
    ollama:        {label:"本地 Ollama",    base_url:"http://localhost:11434/v1",                      model:""},
    vllm:          {label:"本地 vLLM",      base_url:"http://localhost:8000/v1",                       model:""}
  };

  function el(id) { return document.getElementById(id); }

  function append(line, cls) {
    var log = el("log");
    if (log.firstChild && log.firstChild.className === "empty") log.innerHTML = "";
    var d = document.createElement("div");
    d.className = cls || "plain";
    d.textContent = line;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  /* 四步进度：markStep(n,state) —— n 之前全部变绿 done，n 高亮，之后待办 */
  function markStep(n, state) {
    for (var i = 1; i <= 3; i++) {
      var s = el("s" + i);
      if (!s) continue;
      if (i === n) s.className = "step " + state;
      else if (i < n) s.className = "step done";
      else s.className = "step";
    }
  }

  function appendClassified(line) {
    var cls = "plain";
    if (line.indexOf("[import]") === 0) cls = "info";
    if (line.indexOf("[distill]") === 0 || line.indexOf("[export]") === 0 || line.indexOf("[buzz]") === 0) cls = "ok";
    if (line.indexOf(T.warn_marker) >= 0) cls = "warn";
    append(line, cls);
    if (line.indexOf("[import]") === 0) markStep(2, "active");   // 原料导入完成 → 蒸馏中
    if (line.indexOf("[export]") === 0) markStep(3, "active");   // 蒸馏完成 → 成品中
  }

  /* 由 Python 端 evaluate_js 实时推送日志 */
  window.__log = function (line) { appendClassified(line); };

  function setStatus(text, cls) {
    var s = el("file_status");
    s.className = "file-status " + (cls || "");
    s.textContent = text;
  }

  /* ---- 供应商选择：自动映射 base_url + 匹配默认模型名 ---- */
  function onProvider() {
    var p = PROVIDERS[el("provider").value];
    if (p) {
      el("base_url").value = p.base_url;
      el("model").value = p.model;   // 自动匹配模型名；自定义模型请直接改 model 输入框
    } else {
      el("base_url").value = "";
      el("model").value = "";
    }
  }

  /* ---- 来源平台：切换后重新识别；无方向标记的平台提示填昵称 ---- */
  function onSource() {
    var s = el("source").value;
    var needSelf = (s === "telegram" || s === "whatsapp" || s === "meta" || s === "generic" || s === "discord" || s === "slack" || s === "imessage" || s === "qq");
    el("self_name").placeholder = needSelf ? T.self_required : T.self_optional;
    if (el("chat").value.trim()) inspectChat();   // 已有文件 → 按新平台重识别
  }

  /* ---- 文件选择：记录路径并显示在拖拽区 ---- */
  function setFile(path) {
    el("chat").value = path;
    el("drop_hint").textContent = T.selected + path;
    el("dropzone").style.borderColor = "var(--ok)";
  }

  /* ---- 拖拽上传 ---- */
  function onDragOver(e) {
    e.preventDefault();
    el("dropzone").classList.add("over");
    e.dataTransfer.dropEffect = "copy";
  }
  function onDragLeave(e) {
    e.preventDefault();
    el("dropzone").classList.remove("over");
  }
  function onDrop(e) {
    e.preventDefault();
    el("dropzone").classList.remove("over");
    var f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) { setStatus(T.no_file, "warn"); return; }
    markStep(1, "active");   // 拖入即进入步骤 1（与 pick() 一致）
    setStatus(T.detecting);
    var reader = new FileReader();
    reader.onload = function (ev) {
      var b64 = ev.target.result.split(",")[1];   // data:...;base64,
      pywebview.api.import_chat(f.name, b64, el("source").value).then(function (res) {
        if (res.ok) { setFile(res.path); setStatus(T.detected.replace("{format}", res.format).replace("{count}", res.count), "ok"); }
        else { setStatus(T.failed_detect.replace("{error}", res.error), "err"); }
      });
    };
    reader.readAsDataURL(f);
  }

  function pick() {
    pywebview.api.open_file().then(function (path) {
      if (path) { setFile(path); inspectChat(); }
      /* 空路径 = 用户取消选择（或环境无 tkinter）：静默，不弹误导性提示 */
    });
  }

  /* ---- 格式识别：JSON / TXT / 不支持 + 消息数（含自动识别平台） ---- */
  function inspectChat() {
    var path = el("chat").value.trim();
    if (!path) { setStatus(""); return; }
    setStatus(T.detecting);
    pywebview.api.inspect_chat(path, el("source").value).then(function (res) {
      if (res.ok) {
        markStep(1, "active");   // 原料导入：已选文件
        setStatus(T.detected.replace("{format}", res.format).replace("{count}", res.count), "ok");
      } else {
        markStep(1, "active");
        setStatus(T.failed_detect.replace("{error}", res.error), "err");
      }
    });
  }

  function start() {
    var chat = el("chat").value.trim();
    var name = el("name").value.trim();
    var base_url = el("base_url").value.trim();
    var api_key = el("api_key").value.trim();
    var model = el("model").value.trim();
    var fieldLabels = T.fields.split("|");
    var missing = [];
    if (!chat) missing.push(fieldLabels[0]);
    if (!name) missing.push(fieldLabels[1]);
    if (!base_url) missing.push(fieldLabels[2]);
    if (!api_key) missing.push(fieldLabels[3]);
    if (!model) missing.push(fieldLabels[4]);
    if (missing.length) {
      append(T.fill_first.replace("{missing}", missing.join(T.sep)), "err");
      return;
    }

    var go = el("go");
    go.disabled = true;
    el("spinner").classList.remove("hidden");
    el("go_text").textContent = T.distilling;
    el("log").innerHTML = "";
    el("success_banner").classList.remove("show");
    markStep(2, "active");   // 原料就绪 → 蒸馏中

    pywebview.api.start(chat, name, base_url, api_key, model, el("with_memory").checked, el("profile").value.trim(), el("self_name").value.trim(), el("source").value, el("fix").value.trim()).then(function (res) {
      go.disabled = false;
      el("spinner").classList.add("hidden");
      el("go_text").textContent = T.start;
      if (res.ok) {
        if (!res.streamed) res.logs.forEach(appendClassified);   // 流式失败时补打
        var exportPath = "build/export/";
        var exportRe = new RegExp(T.export_re);
        (res.logs || []).forEach(function (l) {
          var m = l.match(exportRe);
          if (l.indexOf("[export]") === 0 && m) exportPath = m[1];
        });
        el("success_path").textContent = exportPath;
        el("success_banner").classList.add("show");
        markStep(3, "active");   // 蒸馏完成 → 导出/测试就绪
        el("export_card").style.display = "";
        el("chat_card").style.display = "";
        el("eval_card").style.display = "";
        var bb = el("buzz_btn");
        bb.classList.remove("btn-pulse"); void bb.offsetWidth; bb.classList.add("btn-pulse");
        append(T.done.replace("{path}", exportPath), "ok");
      } else {
        append(T.error_prefix + res.error, "err");
      }
    });
  }

  /* 一键导入到 buzz：不填名称也会导入全部成品（高容错） */
  function buzzImport() {
    // buzz 导入是步骤 3 的子操作
    pywebview.api.import_buzz(el("name").value.trim()).then(function (res) {
      (res.logs || []).forEach(appendClassified);
      // buzz 导入完成（步骤 3 已在导出时完成）
      else if (res.error) append(T.error_prefix + res.error, "err");
      // 无成品时 res.ok=false 且无 error：日志里已有友好提示，步骤 4 不变绿误导
    });
  }

  /* ---- 多格式导出 ---- */
  function exportPersona() {
    var name = el("name").value.trim();
    if (!name) { append("请先填写人物名称", "err"); return; }
    var fmt = el("export_fmt").value;
    el("export_status").textContent = "正在导出...";
    el("export_status").className = "file-status";
    pywebview.api.export_person(name, fmt).then(function (res) {
      if (res.ok) {
        el("export_status").textContent = "已导出: " + res.paths.join(", ");
        el("export_status").className = "file-status ok";
        markStep(3, "done");  // 导出完成 → 步骤 3 变绿
      } else {
        el("export_status").textContent = "导出失败: " + res.error;
        el("export_status").className = "file-status err";
      }
    });
  }

  /* ---- 聊天测试 ---- */
  function sendChat() {
    var input = el("chat_input");
    var msg = input.value.trim();
    if (!msg) return;
    var name = el("name").value.trim() || "TA";
    input.value = "";
    appendChatMsg("你", msg);
    appendChatMsg(name, "正在思考...", "thinking");
    pywebview.api.chat(name, msg).then(function (res) {
      removeThinking();
      if (res.ok) { appendChatMsg(name, res.reply); }
      else { appendChatMsg(name, "[错误] " + res.error, "err"); }
    });
  }
  function appendChatMsg(role, content, cls) {
    var box = el("chat_msgs");
    if (box.firstChild && box.firstChild.className === "empty") box.innerHTML = "";
    var d = document.createElement("div");
    d.style.marginBottom = "6px"; d.style.lineHeight = "1.6"; d.style.fontSize = "13px";
    var label = document.createElement("b");
    label.textContent = role + "：";
    label.style.color = (role === "你") ? "var(--accent)" : "var(--ok)";
    d.appendChild(label);
    var span = document.createElement("span");
    span.textContent = content;
    if (cls === "err") span.style.color = "var(--err)";
    if (cls === "thinking") { span.style.color = "var(--placeholder)"; span.id = "chat_thinking"; }
    d.appendChild(span); box.appendChild(d); box.scrollTop = box.scrollHeight;
  }
  function removeThinking() { var t = el("chat_thinking"); if (t && t.parentElement) t.parentElement.remove(); }

  /* ---- 自动评分 ---- */
  function runEvaluate() {
    var name = el("name").value.trim();
    if (!name) { append("请先填写人物名称", "err"); return; }
    el("eval_summary").textContent = "正在评分...";
    el("eval_score").textContent = "...";
    el("eval_dims").textContent = ""; el("eval_suggestions").textContent = "";
    pywebview.api.evaluate(name).then(function (res) {
      if (res.ok) {
        var r = res.result, score = r.overall || 0;
        el("eval_score").textContent = score;
        el("eval_score").style.color = score >= 70 ? "var(--ok)" : (score >= 40 ? "var(--warn)" : "var(--err)");
        el("eval_summary").textContent = r.summary || "";
        el("eval_dims").textContent = "真实感 " + (r.authenticity||0) + "/10 · 一致性 " + (r.consistency||0) + "/10 · 表达力 " + (r.expression||0) + "/10 · 情感 " + (r.emotional_depth||0) + "/10";
        el("eval_suggestions").textContent = (r.suggestions || []).map(function(s){return "💡 "+s}).join("
");
      } else { el("eval_score").textContent = "!"; el("eval_summary").textContent = "评分失败: " + res.error; }
    });
  }

  /* 初始化：key 按钮文案随语言 + 恢复切语言前的表单状态 */
  el("key_toggle").textContent = T.show_key;
  restoreState();
</script>
</body>
</html>
"""


class Api:
    """暴露给前端的 js_api：文件选择 + 格式识别 + 蒸馏管线 + 导入 buzz。

    注意：此类实例会被 pywebview 递归枚举，绝不能持有 Window/native 等非可调用对象属性。
    """

    def __init__(self, lang: str = "zh"):
        self.lang = lang if lang in ("zh", "en") else "zh"
        self._pending_state = ""   # 切语言前的表单状态 JSON（重载后恢复，下划线避开桥接枚举）
        self._lang_lock = threading.Lock()  # 保护 lang / _pending_state 跨线程访问

    def set_lang(self, lang: str, state: str = "") -> bool:
        """切换界面语言。state 为 JS 采集的表单状态 JSON，重载后恢复（切换不再清空输入）。

        不能同步 load_html：那会销毁 pywebview 的回调表（_returnValuesCallbacks），
        本 js_api 调用返回时就无法投递结果 → TypeError。改为更新语言后延迟重载，
        让返回值先送达旧页面。
        """
        lang = lang if lang in ("zh", "en") else "zh"
        try:
            obj = json.loads(state) if state else None
            pending = json.dumps(obj, ensure_ascii=False) if isinstance(obj, dict) else ""
        except Exception:
            pending = ""
        with self._lang_lock:
            self._pending_state = pending
            if lang != self.lang:
                self.lang = lang
                threading.Timer(0.15, self._apply_lang).start()
        return True

    def _apply_lang(self) -> None:
        try:
            with self._lang_lock:
                current_lang = self.lang
                state = self._pending_state
            if _GUI_WINDOW is not None:
                _GUI_WINDOW.load_html(_build_html(current_lang, state))
        except Exception:
            pass  # 竞态容错：返回值回调已尽力先送达
        try:
            # 标题随语言切换；单独容错：失败不影响界面重载本身（部分后端需在主线程调）
            if _GUI_WINDOW is not None:
                _GUI_WINDOW.set_title(_GUI_TITLES[current_lang])
        except Exception:
            pass

    def open_file(self) -> str:
        try:
            from tkinter import filedialog
        except Exception:
            return ""  # 无 tkinter（精简版 Python）→ 返回空，前端提示改用拖拽
        try:
            path = filedialog.askopenfilename(
                title="选择聊天文件" if self.lang == "zh" else "Choose chat file",
                filetypes=[("聊天文件", "*.json *.txt") if self.lang == "zh" else ("Chat file", "*.json *.txt"),
                           ("所有文件", "*.*") if self.lang == "zh" else ("All files", "*.*")])
            return path or ""
        except Exception:
            return ""

    def inspect_chat(self, path: str, source: str = "auto") -> dict:
        """识别聊天文件格式与消息数，给低门槛用户即时反馈。"""
        try:
            fmt = source if source and source != "auto" else detect_source(path)
            # 传 fmt 给 parse_messages 避免内部重复 detect_source
            msgs = parse_messages(path, source=fmt)
            return {"ok": True, "format": SOURCE_LABELS.get(fmt, fmt), "count": len(msgs), "source": fmt}
        except Exception as e:
            return {"ok": False, "error": _tr_error(str(e), self.lang)}

    def import_chat(self, filename: str, b64: str, source: str = "auto") -> dict:
        """拖拽上传：前端无法拿到本地路径，改为收 base64 内容落盘到 build/dropped/。"""
        try:
            data = base64.b64decode(b64)
            ext = Path(filename).suffix.lower()
            if ext not in (".json", ".txt"):
                ext = ".txt"
            dropped = _gui_workdir() / "dropped"
            dropped.mkdir(parents=True, exist_ok=True)
            # 清理 24 小时前的拖拽落盘，避免反复拖拽堆积垃圾文件（失败不阻断主流程）
            cutoff = time.time() - 24 * 3600
            for old in dropped.iterdir():
                try:
                    if old.is_file() and old.stat().st_mtime < cutoff:
                        old.unlink()
                except OSError:
                    pass
            stem = safe_filename(Path(filename).stem or "chat")
            p = dropped / f"{stem}-{uuid.uuid4().hex[:6]}{ext}"
            p.write_bytes(data)
            # 识别格式（一次）后把 source 传给 parse_messages，避免重复 detect_source
            fmt = source if source and source != "auto" else detect_source(str(p))
            msgs = parse_messages(str(p), source=fmt)
            return {"ok": True, "path": str(p), "format": SOURCE_LABELS.get(fmt, fmt), "count": len(msgs)}
        except Exception as e:
            return {"ok": False, "error": _tr_error(str(e), self.lang)}

    def start(self, chat: str, name: str, base_url: str, api_key: str, model: str, with_memory: bool = False, profile: str = "", self_name: str = "", source: str = "auto", fix: str = "") -> dict:
        model_config = {"base_url": base_url, "api_key": api_key, "model": model}
        streamed = False

        def on_log(line: str) -> None:
            nonlocal streamed
            try:
                if _GUI_WINDOW is None:
                    return
                result = _GUI_WINDOW.evaluate_js(f"window.__log({json.dumps(line, ensure_ascii=False)}); true")
                if result is not False and result is not None:
                    streamed = True
            except Exception:
                pass

        try:
            logs = run_pipeline(chat, name, model_config, str(_gui_workdir()), with_memory, on_log=on_log, manual_profile=profile, self_name=self_name, source=source, lang=self.lang, fix=fix)
            return {"ok": True, "logs": logs, "streamed": streamed}
        except Exception as e:  # noqa: BLE001 — 边界统一转给前端展示
            return {"ok": False, "error": _tr_error(str(e), self.lang)}

    def import_buzz(self, name: str) -> dict:
        try:
            logs = import_to_buzz(name, str(_gui_workdir()), lang=self.lang)
            # ok 只认"真有成品可导"：没有成品时日志里已有友好提示，但步骤 4 不该变绿误导用户
            export_dir = _gui_workdir() / "export"
            ok = export_dir.exists() and any(export_dir.glob("*.agent.json"))
            return {"ok": ok, "logs": logs}
        except Exception as e:
            return {"ok": False, "error": _tr_error(str(e), self.lang), "logs": []}

    def export_person(self, name: str, fmt: str = "all") -> dict:
        """多格式导出：text/buzz/all。"""
        try:
            from ..core.models import PersonaDoc
            from ..core.safe import safe_filename
            from .. import exporters  # noqa: F401
            from ..core.plugins import export_all as _export_all
            safe = safe_filename(name)
            persona_path = _gui_workdir() / "persona" / f"{safe}.json"
            if not persona_path.exists():
                return {"ok": False, "error": _tr_error("未找到 persona，请先蒸馏", self.lang)}
            doc = PersonaDoc.model_validate(json.loads(persona_path.read_text(encoding="utf-8")))
            export_dir = _gui_workdir() / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            # 记忆导出：从 persona JSON 判断（with_memory 在 distill 时已决定）
            include_memory = bool(doc.memory)
            if fmt == "all":
                paths = _export_all(doc, str(export_dir), include_memory=include_memory)
            else:
                from ..core.plugins import get_exporter
                adapter = get_exporter(fmt)
                if not adapter:
                    return {"ok": False, "error": f"未知格式: {fmt}"}
                p = adapter.export(doc, str(export_dir), include_memory=include_memory)
                paths = [p] if p else []
            return {"ok": True, "paths": paths}
        except Exception as e:
            return {"ok": False, "error": _tr_error(str(e), self.lang)}

    def chat(self, name: str, message: str) -> dict:
        """聊天测试。"""
        try:
            from ..core.chat import create_session
            from ..core.safe import safe_filename
            safe = safe_filename(name)
            persona_path = _gui_workdir() / "persona" / f"{safe}.json"
            if not persona_path.exists():
                return {"ok": False, "error": "未找到 persona，请先蒸馏"}
            if not hasattr(self, "_chat_sessions"):
                self._chat_sessions = {}
            session_key = str(persona_path)
            if session_key not in self._chat_sessions:
                file_cfg = load_config(resolve_config_path())
                model_cfg = file_cfg.get("model") or {}
                if not model_cfg.get("api_key"):
                    return {"ok": False, "error": "未配置模型 API key"}
                self._chat_sessions[session_key] = create_session(str(persona_path), {"model": model_cfg})
            session = self._chat_sessions[session_key]
            reply = session.send(message)
            return {"ok": True, "reply": reply}
        except Exception as e:
            return {"ok": False, "error": _tr_error(str(e), self.lang)}

    def evaluate(self, name: str) -> dict:
        """自动评分。"""
        try:
            from ..core.evaluate import auto_evaluate
            from ..core.safe import safe_filename
            safe = safe_filename(name)
            persona_path = _gui_workdir() / "persona" / f"{safe}.json"
            if not persona_path.exists():
                return {"ok": False, "error": "未找到 persona，请先蒸馏"}
            file_cfg = load_config(resolve_config_path())
            model_cfg = file_cfg.get("model") or {}
            if not model_cfg.get("api_key"):
                return {"ok": False, "error": "未配置模型 API key"}
            result = auto_evaluate(str(persona_path), {"model": model_cfg}, n_scenarios=5)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": _tr_error(str(e), self.lang)}


def run_gui(lang: str = "auto") -> None:
    """启动 pywebview 新拟物派桌面界面。lang: auto/zh/en。"""
    global _GUI_WINDOW
    if lang not in ("zh", "en"):
        lang = _detect_lang()
    api = Api(lang)
    window = webview.create_window(
        _GUI_TITLES[lang],
        html=_build_html(lang),
        js_api=api,
        width=780, height=940,
        min_size=(620, 720),
        background_color="#e0e5ec",
    )
    _GUI_WINDOW = window
    webview.start()
