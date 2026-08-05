"""Alchemy Hive 桌面界面（pywebview 新拟物派 Neumorphism）。

浅灰同色系 + 双重阴影（右下暗 / 左上亮）模拟光源：凸起=可交互，凹陷=输入区/激活。
Python 端只做 js_api 桥接，业务逻辑复用 actions.run_pipeline。

面向低门槛用户的傻瓜化处理：
- 聊天文件支持拖拽上传 + 即时格式识别（JSON/TXT/消息数）
- 模型供应商下拉选择，自动映射 base_url 并自动匹配默认模型名，也可自定义
"""
import base64
import json
import uuid
from pathlib import Path

import webview

from .actions import run_pipeline
from ..core.parser import parse_messages
from ..core.safe import safe_filename
from ..buzz.importing import import_to_buzz

# 模块级窗口引用：绝不能挂在 js_api 实例上。pywebview 会用 dir()/getattr() 递归枚举
# js_api 的整个对象图来生成 JS 桥接函数表，把 Window 挂在实例上会把递归拖入
# window.native 的 .NET/COM 无障碍对象图 → RecursionError → 窗口无法加载。
_GUI_WINDOW = None

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
    font-family: "PingFang SC", "Microsoft YaHei UI", -apple-system, sans-serif;
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

  /* 步骤指示：当前步高亮蓝 */
  .steps { display: flex; gap: 14px; font-size: 13px; color: var(--muted); margin: 18px 0 10px; font-weight: 600; }
  .steps .sep { opacity: .4; font-weight: 400; }
  .steps .active { color: var(--accent); }

  /* 卡片：凸起 */
  .card {
    background: var(--bg-elem);
    border-radius: var(--radius-card);
    box-shadow: 10px 10px 20px var(--dark), -10px -10px 20px var(--light);
    padding: 20px 22px;
    margin-bottom: 18px;
  }
  .card .label { font-size: 12px; color: var(--muted); margin-bottom: 12px; }
  .row { display: flex; gap: 10px; }

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

  /* 日志：突出显示面板（凹陷 + 大字号 + 深字） */
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
  }
  .log .info { color: var(--accent); }
  .log .ok { color: var(--ok); }
  .log .warn { color: var(--warn); }
  .log .err { color: var(--err); }
  .log .plain { color: var(--text); }
  .log .empty { color: var(--placeholder); }
</style>
</head>
<body>
  <div class="brand">
    <h1>Alchemy Hive</h1>
    <p>把微信聊天蒸馏成 AI 朋友</p>
  </div>

  <div class="steps">
    <span class="active" id="s1">1 原料</span><span class="sep">·</span>
    <span id="s2">2 蒸馏</span><span class="sep">·</span>
    <span id="s3">3 成品</span>
  </div>

  <div class="card">
    <div class="label">第一步 · 原料 — 把微信聊天记录文件拖进来，或点「浏览」选择</div>
    <div class="dropzone" id="dropzone"
         ondragover="onDragOver(event)" ondragleave="onDragLeave(event)" ondrop="onDrop(event)">
      <div id="drop_hint">把聊天文件（WeFlow 导出 .json 或微信 .txt）拖到这里</div>
      <div class="row" style="justify-content:center; margin-top:12px;">
        <button class="ghost" onclick="pick()">浏览文件…</button>
      </div>
    </div>
    <input type="hidden" id="chat">
    <div class="file-status" id="file_status"></div>
  </div>

  <div class="card">
    <div class="label">第二步 · 蒸馏设置</div>
    <input class="field" id="name" placeholder="Ta 的名称（如：小明）">
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
    <input class="field" id="api_key" type="password" placeholder="API key（向模型供应商申请，必需）">
    <div class="hint">选择供应商后会自动填好地址和模型名；想用别的模型直接改这两格即可。API key 请去对应供应商官网申请。</div>
    <div class="spacer"></div>
    <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);cursor:pointer;">
      <input type="checkbox" id="with_memory" style="accent-color:var(--accent);width:15px;height:15px;">
      导出共同记忆（明文、含真实内容，默认不含）
    </label>
  </div>

  <button class="primary" id="go" onclick="start()">
    <span class="spinner hidden" id="spinner"></span><span id="go_text">开始蒸馏</span>
  </button>

  <div class="row" style="margin:-14px 0 16px; justify-content:center;">
    <button class="ghost" onclick="buzzImport()">导入到 buzz · 打开导出文件夹并复制路径</button>
  </div>

  <div class="log-wrap">
    <div class="log-label">运行结果 · 日志</div>
    <div class="log" id="log">
      <span class="empty">运行后在这里查看步骤日志…</span>
    </div>
  </div>

<script>
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

  function appendClassified(line) {
    var cls = "plain";
    if (line.indexOf("[import]") === 0) cls = "info";
    if (line.indexOf("[distill]") === 0 || line.indexOf("[export]") === 0 || line.indexOf("[buzz]") === 0) cls = "ok";
    if (line.indexOf("提醒") >= 0) cls = "warn";
    append(line, cls);
    if (line.indexOf("[import]") === 0) el("s1").className = "active";
    if (line.indexOf("[distill]") === 0) el("s2").className = "active";
    if (line.indexOf("[export]") === 0) el("s3").className = "active";
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

  /* ---- 文件选择：记录路径并显示在拖拽区 ---- */
  function setFile(path) {
    el("chat").value = path;
    el("drop_hint").textContent = "已选择：" + path;
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
    if (!f) { setStatus("没有拿到文件，请改用「浏览文件」选择。", "warn"); return; }
    setStatus("正在识别文件格式…");
    var reader = new FileReader();
    reader.onload = function (ev) {
      var b64 = ev.target.result.split(",")[1];   // data:...;base64,
      pywebview.api.import_chat(f.name, b64).then(function (res) {
        if (res.ok) { setFile(res.path); setStatus("已识别：" + res.format + " · " + res.count + " 条消息", "ok"); }
        else { setStatus("无法识别：" + res.error, "err"); }
      });
    };
    reader.readAsDataURL(f);
  }

  function pick() {
    pywebview.api.open_file().then(function (path) {
      if (path) { setFile(path); inspectChat(); }
    });
  }

  /* ---- 格式识别：JSON / TXT / 不支持 + 消息数 ---- */
  function inspectChat() {
    var path = el("chat").value.trim();
    if (!path) { setStatus(""); return; }
    setStatus("正在识别文件格式…");
    pywebview.api.inspect_chat(path).then(function (res) {
      if (res.ok) {
        el("s1").className = "active";
        setStatus("已识别：" + res.format + " · " + res.count + " 条消息", "ok");
      } else {
        el("s1").className = "active";
        setStatus("无法识别：" + res.error, "err");
      }
    });
  }

  function start() {
    var chat = el("chat").value.trim();
    var name = el("name").value.trim();
    var base_url = el("base_url").value.trim();
    var api_key = el("api_key").value.trim();
    var model = el("model").value.trim();
    var missing = [];
    if (!chat) missing.push("聊天文件");
    if (!name) missing.push("Ta 的名称");
    if (!base_url) missing.push("模型地址");
    if (!api_key) missing.push("API key");
    if (!model) missing.push("模型名");
    if (missing.length) {
      append("请先填写：" + missing.join("、") + "。", "err");
      return;
    }

    var go = el("go");
    go.disabled = true;
    el("spinner").classList.remove("hidden");
    el("go_text").textContent = "正在蒸馏中…";
    el("log").innerHTML = "";
    el("s1").className = "active";

    pywebview.api.start(chat, name, base_url, api_key, model, el("with_memory").checked).then(function (res) {
      go.disabled = false;
      el("spinner").classList.add("hidden");
      el("go_text").textContent = "开始蒸馏";
      if (res.ok) {
        if (!res.streamed) res.logs.forEach(appendClassified);   // 流式失败时补打
        append("完成 可在 build/export/ 找到 .agent.json，点击下方「导入到 buzz」即可。", "ok");
        el("s1").className = "active"; el("s2").className = "active"; el("s3").className = "active";
      } else {
        append("错误: " + res.error, "err");
      }
    });
  }

  /* 导入到 buzz：打开导出文件夹 + 复制文件完整路径 */
  function buzzImport() {
    var name = el("name").value.trim();
    if (!name) { append("请先填写 Ta 的名称。", "err"); return; }
    pywebview.api.import_buzz(name).then(function (res) {
      (res.logs || []).forEach(appendClassified);
      if (!res.ok) append("错误: " + res.error, "err");
    });
  }
</script>
</body>
</html>
"""


class Api:
    """暴露给前端的 js_api：文件选择 + 格式识别 + 蒸馏管线 + 导入 buzz。

    注意：此类实例会被 pywebview 递归枚举，绝不能持有 Window/native 等非可调用对象属性。
    """

    def open_file(self) -> str:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择聊天文件",
            filetypes=[("聊天文件", "*.json *.txt"), ("所有文件", "*.*")])
        return path or ""

    def inspect_chat(self, path: str) -> dict:
        """识别聊天文件格式与消息数，给低门槛用户即时反馈。"""
        try:
            msgs = parse_messages(path)
            fmt = "WeFlow JSON" if path.lower().endswith(".json") else "微信 TXT"
            return {"ok": True, "format": fmt, "count": len(msgs)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def import_chat(self, filename: str, b64: str) -> dict:
        """拖拽上传：前端无法拿到本地路径，改为收 base64 内容落盘到 build/dropped/。"""
        try:
            data = base64.b64decode(b64)
            ext = Path(filename).suffix.lower()
            if ext not in (".json", ".txt"):
                ext = ".txt"
            dropped = Path("build") / "dropped"
            dropped.mkdir(parents=True, exist_ok=True)
            stem = safe_filename(Path(filename).stem or "chat")
            p = dropped / f"{stem}-{uuid.uuid4().hex[:6]}{ext}"
            p.write_bytes(data)
            msgs = parse_messages(str(p))
            fmt = "WeFlow JSON" if ext == ".json" else "微信 TXT"
            return {"ok": True, "path": str(p), "format": fmt, "count": len(msgs)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def start(self, chat: str, name: str, base_url: str, api_key: str, model: str, with_memory: bool = False) -> dict:
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
            logs = run_pipeline(chat, name, model_config, "build", with_memory, on_log=on_log)
            return {"ok": True, "logs": logs, "streamed": streamed}
        except Exception as e:  # noqa: BLE001 — 边界统一转给前端展示
            return {"ok": False, "error": str(e)}

    def import_buzz(self, name: str) -> dict:
        try:
            logs = import_to_buzz(name, "build")
            return {"ok": True, "logs": logs}
        except Exception as e:
            return {"ok": False, "error": str(e), "logs": []}


def run_gui() -> None:
    """启动 pywebview 新拟物派桌面界面。"""
    global _GUI_WINDOW
    api = Api()
    window = webview.create_window(
        "Alchemy Hive · 把微信聊天蒸馏成 AI 朋友",
        html=_HTML,
        js_api=api,
        width=780, height=860,
        min_size=(620, 700),
        background_color="#e0e5ec",
    )
    _GUI_WINDOW = window
    webview.start()
