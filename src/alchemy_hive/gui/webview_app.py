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
    "把微信聊天蒸馏成 AI 朋友，导入 <b>buzz</b> 随时开聊、组建无数个 AI 社群":
        "Distill your WeChat chats into AI friends, drop them into <b>buzz</b> and chat anytime.",
    "本项目完全开源，不会获取您的任何个人信息和 API key。":
        "Open source — we never collect your personal data or API keys.",
    "原料导入 · 选导出平台（自动识别也行），把聊天文件拖进来":
        "Step 1 · Choose a platform (auto-detect works), then drop your chat file",
    "蒸馏人物 · 性格画像与模型（画像越具体越像 TA）":
        "Step 2 · Persona & model (the more specific the profile, the closer it gets)",
    "导入buzz · 把 AI 朋友装进 buzz 开聊（buzz 是免费开源 AI 聊天室，可组建无数个社群）":
        "Import to buzz · put your AI friend into buzz (free & open source — build any number of communities)",
    "原料导入": "Import",
    "蒸馏人物": "Distill",
    "成品文件": "Export",
    "导入buzz": "Into buzz",
    "自动识别（推荐）": "Auto-detect (Recommended)",
    "微信（WeFlow 导出）": "WeChat (via WeFlow)",
    "微信 txt": "WeChat txt",
    "其他（通用字段解析）": "Other (generic)",
    "把聊天文件拖到这里（微信 / Telegram / WhatsApp / Instagram / Facebook 导出）":
        "Drop your chat file here (WeChat / Telegram / WhatsApp / Instagram / Facebook export)",
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

_HTML = None  # placeholder — imported below

from .html_template import _HTML


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
            if fmt == "all":
                paths = _export_all(doc, str(export_dir))
            else:
                from ..core.plugins import get_exporter
                adapter = get_exporter(fmt)
                if not adapter:
                    return {"ok": False, "error": f"未知格式: {fmt}"}
                p = adapter.export(doc, str(export_dir))
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
