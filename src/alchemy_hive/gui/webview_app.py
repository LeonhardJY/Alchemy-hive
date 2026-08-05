"""Alchemy Hive 桌面界面（pywebview 新拟物派 Neumorphism）。

浅灰同色系 + 双重阴影（右下暗 / 左上亮）模拟光源：凸起=可交互，凹陷=输入区/激活。
Python 端只做 js_api 桥接，业务逻辑复用 actions.run_pipeline。
"""
import webview

from .actions import run_pipeline
from ..core.distill import DistillError

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

  /* 输入框：凹陷，文字清晰 */
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
  .spacer { height: 14px; }

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

  /* 日志：突出显示面板（凹陷 + 大字号 + 深字） */
  .log-wrap { margin-top: 2px; }
  .log-label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
  .log {
    background: var(--bg-elem);
    border-radius: var(--radius-card);
    box-shadow: inset 8px 8px 16px var(--dark), inset -8px -8px 16px var(--light);
    padding: 16px 20px;
    min-height: 210px;
    max-height: 320px;
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
    <div class="label">第一步 · 原料 — 聊天文件（WeFlow 导出 JSON 或微信 txt）</div>
    <div class="row">
      <input class="field" id="chat" placeholder="选择或输入聊天文件路径…">
      <button class="ghost" onclick="pick()">浏览</button>
    </div>
  </div>

  <div class="card">
    <div class="label">第二步 · 蒸馏设置（LLM 必需）</div>
    <input class="field" id="name" placeholder="Ta 的名称">
    <div class="spacer"></div>
    <input class="field" id="base_url" placeholder="模型地址 base_url，比如 https://api.deepseek.com/v1">
    <div class="spacer"></div>
    <input class="field" id="api_key" type="password" placeholder="API key（必需）">
    <div class="spacer"></div>
    <input class="field" id="model" placeholder="模型名 model，比如 deepseek-chat">
  </div>

  <button class="primary" id="go" onclick="start()">开始蒸馏</button>

  <div class="log-wrap">
    <div class="log-label">运行结果 · 日志</div>
    <div class="log" id="log">
      <span class="empty">运行后在这里查看步骤日志…</span>
    </div>
  </div>

<script>
  function el(id) { return document.getElementById(id); }

  function pick() {
    pywebview.api.open_file().then(function (path) {
      if (path) el("chat").value = path;
    });
  }

  function append(line, cls) {
    var log = el("log");
    if (log.firstChild && log.firstChild.className === "empty") log.innerHTML = "";
    var d = document.createElement("div");
    d.className = cls || "plain";
    d.textContent = line;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  function start() {
    var go = el("go");
    go.disabled = true;
    el("log").innerHTML = "";
    pywebview.api.start(
      el("chat").value.trim(), el("name").value.trim(),
      el("base_url").value.trim(), el("api_key").value.trim(), el("model").value.trim()
    ).then(function (res) {
      go.disabled = false;
      if (res.ok) {
        res.logs.forEach(function (l) {
          var cls = "plain";
          if (l.indexOf("[import]") === 0) cls = "info";
          if (l.indexOf("[distill]") === 0 || l.indexOf("[export]") === 0) cls = "ok";
          if (l.indexOf("提醒") >= 0) cls = "warn";
          append(l, cls);
        });
        append("完成 可在 build/export/ 找到 .agent.json，拖入 buzz 桌面端导入。", "ok");
        el("s1").className = "active"; el("s2").className = "active"; el("s3").className = "active";
      } else {
        append("错误: " + res.error, "err");
      }
    });
  }
</script>
</body>
</html>
"""


class Api:
    """暴露给前端的 js_api：文件选择 + 蒸馏管线。"""

    def open_file(self) -> str:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择聊天文件",
            filetypes=[("聊天文件", "*.json *.txt"), ("所有文件", "*.*")])
        return path or ""

    def start(self, chat: str, name: str, base_url: str, api_key: str, model: str) -> dict:
        model_config = {"base_url": base_url, "api_key": api_key, "model": model}
        try:
            logs = run_pipeline(chat, name, model_config, "build")
            return {"ok": True, "logs": logs}
        except (DistillError, Exception) as e:  # noqa: BLE001 — 边界统一转给前端展示
            return {"ok": False, "error": str(e)}


def run_gui() -> None:
    """启动 pywebview 新拟物派桌面界面。"""
    api = Api()
    window = webview.create_window(
        "Alchemy Hive · 把微信聊天蒸馏成 AI 朋友",
        html=_HTML,
        js_api=api,
        width=780, height=780,
        min_size=(620, 640),
        background_color="#e0e5ec",
    )
    webview.start()
