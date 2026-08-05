"""weflow-agent 桌面界面（玻璃拟态 glassmorphism，Canvas 自绘薄壳）。

业务逻辑在 actions.py。视觉：深色渐变背景上的半透明圆角玻璃卡片、玻璃蓝圆角主按钮。
输入框用灰色 placeholder（不填示例值）。主操作按钮固定在卡片与日志之间，不会被挤压。
"""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import END

import ttkbootstrap as ttk

from .actions import run_pipeline
from ..core.distill import DistillError

# ── 玻璃拟态色板 ────────────────────────────────────────────
BG_TOP = "#0E1424"          # 渐变顶：深蓝黑
BG_BOTTOM = "#1A2440"       # 渐变底：深紫蓝
GLASS = "#202A47"           # 卡片玻璃色（半透明白于深蓝上的近似）
GLASS_BORDER = "#3D4E78"    # 卡片描边（半透明白 20%）
ACCENT = "#5B8DEF"          # 玻璃蓝（主按钮）
ACCENT_ACTIVE = "#7AA3F2"   # 按钮悬停
TEXT = "#E8EDF7"            # 主文本
MUTED = "#93A1C4"           # 次要文本
PLACEHOLDER = "#66728F"     # placeholder 灰
INPUT_BG = "#1B2540"        # 输入框底色
LOGBG = "#161E36"           # 日志区底色
SUCCESS = "#4CD97B"         # 成功绿
DANGER = "#FF5D5D"          # 错误红

FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_BRAND = ("Microsoft YaHei UI", 15, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_BUTTON = ("Microsoft YaHei UI", 11, "bold")

W, H = 760, 740  # 固定窗口尺寸


def _round_rect(c, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形。"""
    pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
           x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class PlaceholderEntry(tk.Entry):
    """带灰色占位文本的输入框：聚焦时清空，失焦为空时恢复。tk.Entry 以完全控色。"""

    def __init__(self, master, placeholder: str, show: str | None = None, **kw):
        kw.setdefault("bg", INPUT_BG)
        kw.setdefault("fg", PLACEHOLDER)
        kw.setdefault("insertbackground", TEXT)
        kw.setdefault("relief", "flat")
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", GLASS_BORDER)
        kw.setdefault("highlightcolor", ACCENT)
        kw.setdefault("font", FONT)
        kw.setdefault("show", show)
        super().__init__(master, **kw)
        self._placeholder = placeholder
        self._active = True
        self.insert(0, placeholder)
        self.bind("<FocusIn>", self._on_in)
        self.bind("<FocusOut>", self._on_out)

    def _on_in(self, _e):
        if self._active:
            self.delete(0, END)
            self.configure(fg=TEXT)
            self._active = False

    def _on_out(self, _e):
        if not self.get().strip():
            self.insert(0, self._placeholder)
            self.configure(fg=PLACEHOLDER)
            self._active = True

    def get_value(self) -> str:
        """返回用户实际输入（占位状态时返回空串）。"""
        return "" if self._active else self.get().strip()


class AgentGUI:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("weflow-agent")
        self.root.geometry(f"{W}x{H}")
        self.root.resizable(False, False)
        self.style = root.style
        self._apply_style()
        self._build()

    def _apply_style(self) -> None:
        s = self.style
        s.configure(".", font=FONT)
        s.configure("TFrame", background=BG_TOP)
        s.configure("Card.TFrame", background=GLASS)
        s.configure("TLabel", background=BG_TOP, foreground=TEXT)
        s.configure("Card.TLabel", background=GLASS, foreground=TEXT)
        s.configure("Muted.TLabel", background=BG_TOP, foreground=MUTED, font=FONT_SMALL)
        s.configure("Step.TLabel", background=BG_TOP, foreground=MUTED, font=FONT_SMALL)
        s.configure("StepActive.TLabel", background=BG_TOP, foreground=ACCENT, font=FONT_SMALL)

    def _build(self) -> None:
        self.canvas = tk.Canvas(self.root, width=W, height=H,
                                highlightthickness=0, background=BG_TOP)
        self.canvas.pack(fill="both", expand=True)
        self._draw_background()
        self._build_header()
        self._build_steps()
        self._build_upload_card()
        self._build_config_card()
        self._build_primary_button()
        self._build_log_card()
        # 绑定窗口缩放时重绘（固定尺寸下基本不触发）
        self.canvas.bind("<Configure>", lambda e: self._draw_background())

    # ── 背景渐变 ─────────────────────────────────────────────
    def _draw_background(self) -> None:
        self.canvas.delete("bg")
        w = self.canvas.winfo_width() or W
        h = self.canvas.winfo_height() or H
        bands = 36
        for i in range(bands):
            t = i / (bands - 1)
            color = _lerp(BG_TOP, BG_BOTTOM, t)
            y0 = int(h * i / bands)
            y1 = int(h * (i + 1) / bands)
            self.canvas.create_rectangle(0, y0, w, y1, fill=color, outline="", tags="bg")

    # ── 品牌 + 步骤 ──────────────────────────────────────────
    def _build_header(self) -> None:
        self.canvas.create_text(40, 34, anchor="w", text="weflow-agent",
                                fill=TEXT, font=FONT_BRAND, tags="ui")
        self.canvas.create_text(41, 56, anchor="w", text="把微信聊天蒸馏成 AI 朋友",
                                fill=MUTED, font=FONT_SMALL, tags="ui")

    def _build_steps(self) -> None:
        self.step_ids = []
        labels = ["1 原料", "2 蒸馏", "3 成品"]
        for i, label in enumerate(labels):
            x = 150 + i * 90
            fill = ACCENT if i == 0 else MUTED
            self.step_ids.append(self.canvas.create_text(x, 96, anchor="w", text=label,
                                                         fill=fill, font=FONT_SMALL, tags="ui"))

    # ── 卡片容器 ─────────────────────────────────────────────
    def _glass_card(self, x1, y1, x2, y2, title: str) -> ttk.Frame:
        """画圆角玻璃卡片，返回内部内容 frame。"""
        _round_rect(self.canvas, x1, y1, x2, y2, 14,
                    fill=GLASS, outline=GLASS_BORDER, width=1, tags="card")
        self.canvas.create_text(x1 + 20, y1 + 22, anchor="w", text=title,
                                fill=MUTED, font=FONT_SMALL, tags="ui")
        frame = ttk.Frame(self.canvas, style="Card.TFrame")
        self.canvas.create_window(x1 + 20, y1 + 38, anchor="nw",
                                  window=frame, tags="ui")
        return frame

    # ── 第一步 · 原料 ────────────────────────────────────────
    def _build_upload_card(self) -> None:
        frm = self._glass_card(30, 120, W - 30, 220, "第一步 · 原料")
        ttk.Label(frm, text="聊天文件（WeFlow 导出 JSON 或微信 txt）",
                  style="Card.TLabel").pack(anchor="w")
        row = ttk.Frame(frm, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.chat_path = PlaceholderEntry(row, "选择或输入聊天文件路径…")
        self.chat_path.pack(side="left", fill="x", expand=True, ipady=2)
        ttk.Button(row, text="浏览", bootstyle="outline-info",
                   command=self._pick_file).pack(side="left", padx=(8, 0))

    # ── 第二步 · 蒸馏设置 ────────────────────────────────────
    def _build_config_card(self) -> None:
        frm = self._glass_card(30, 240, W - 30, 452, "第二步 · 蒸馏设置")
        self._labeled_placeholder(frm, "Ta 的名称", "name", "输入 Ta 的名称")
        self._labeled_placeholder(frm, "模型地址 base_url", "base_url", "比如 https://api.deepseek.com/v1")
        self._labeled_placeholder(frm, "API key（必需）", "api_key", "粘贴你的 API key", show="*")
        self._labeled_placeholder(frm, "模型名 model", "model", "比如 deepseek-chat")

    def _labeled_placeholder(self, parent: ttk.Frame, label: str, key: str,
                             placeholder: str, show: str | None = None) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").pack(anchor="w", pady=(6, 0))
        entry = PlaceholderEntry(parent, placeholder, show=show)
        setattr(self, key, entry)
        entry.pack(fill="x", ipady=2)

    # ── 主操作按钮（圆角玻璃蓝）──────────────────────────────
    def _build_primary_button(self) -> None:
        bx1, by1, bx2, by2 = 30, 468, W - 30, 512
        self.btn_rect = _round_rect(self.canvas, bx1, by1, bx2, by2, 12,
                                    fill=ACCENT, outline="", tags="btn")
        cx = (bx1 + bx2) / 2
        cy = (by1 + by2) / 2
        self.btn_text = self.canvas.create_text(cx, cy, text="开始蒸馏",
                                                fill="#FFFFFF", font=FONT_BUTTON, tags="btn")
        self.canvas.tag_bind("btn", "<Button-1>", lambda e: self._run())
        self.canvas.tag_bind("btn", "<Enter>", lambda e: self.canvas.itemconfig(self.btn_rect, fill=ACCENT_ACTIVE))
        self.canvas.tag_bind("btn", "<Leave>", lambda e: self.canvas.itemconfig(self.btn_rect, fill=ACCENT))

    # ── 日志卡片 ─────────────────────────────────────────────
    def _build_log_card(self) -> None:
        x1, y1, x2, y2 = 30, 532, W - 30, H - 30
        _round_rect(self.canvas, x1, y1, x2, y2, 14,
                    fill=GLASS, outline=GLASS_BORDER, width=1, tags="card")
        self.canvas.create_text(x1 + 20, y1 + 22, anchor="w", text="日志",
                                fill=MUTED, font=FONT_SMALL, tags="ui")
        self.log = scrolledtext.ScrolledText(self.canvas, height=8, state="disabled",
                                             font=FONT, bg=LOGBG, fg=TEXT,
                                             relief="flat", bd=0, highlightthickness=0,
                                             insertbackground=TEXT)
        self.canvas.create_window(x1 + 20, y1 + 40, anchor="nw",
                                  window=self.log, width=x2 - x1 - 40,
                                  height=y2 - y1 - 56, tags="ui")
        for tag, color in (("ok", SUCCESS), ("info", ACCENT), ("warn", "#F5A623"),
                           ("err", DANGER), ("plain", TEXT)):
            self.log.tag_config(tag, foreground=color)

    # ── 交互 ─────────────────────────────────────────────────
    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择聊天文件",
            filetypes=[("聊天文件", "*.json *.txt"), ("所有文件", "*.*")])
        if path:
            self.chat_path.delete(0, END)
            self.chat_path._active = False
            self.chat_path.configure(fg=TEXT)
            self.chat_path.insert(0, path)

    def _append_log(self, line: str, tag: str = "plain") -> None:
        self.log.configure(state="normal")
        self.log.insert(END, line + "\n", tag)
        self.log.see(END)
        self.log.configure(state="disabled")

    def _run(self) -> None:
        chat = self.chat_path.get_value()
        name = self.name.get_value()
        if not chat or not name:
            messagebox.showwarning("缺少信息", "请先选择聊天文件并填写 Ta 的名称。")
            return
        model_config = {
            "base_url": self.base_url.get_value(),
            "api_key": self.api_key.get_value(),
            "model": self.model.get_value(),
        }
        self.log.configure(state="normal")
        self.log.delete("1.0", END)
        self.log.configure(state="disabled")
        try:
            logs = run_pipeline(chat, name, model_config, "build")
            for line in logs:
                tag = "info" if line.startswith("[import]") else "plain"
                if line.startswith("[distill]") or line.startswith("[export]"):
                    tag = "ok"
                if "提醒" in line:
                    tag = "warn"
                self._append_log(line, tag)
            self._append_log("完成 可在 build/export/ 找到 .agent.json，拖入 buzz 桌面端导入。", "ok")
        except DistillError as e:
            self._append_log(f"错误: {e}", "err")
            messagebox.showerror("蒸馏失败", str(e))
        except Exception as e:  # noqa: BLE001 — GUI 边界统一兜底
            self._append_log(f"错误: {e}", "err")
            messagebox.showerror("出错", str(e))


def _lerp(c1: str, c2: str, t: float) -> str:
    """两个 #RRGGBB 颜色线性插值。"""
    r1, g1, b1 = (int(c1[i:i+2], 16) for i in (1, 3, 5))
    r2, g2, b2 = (int(c2[i:i+2], 16) for i in (1, 3, 5))
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def run_gui() -> None:
    """启动桌面图形界面（玻璃拟态）。"""
    root = ttk.Window(themename="darkly")
    AgentGUI(root)
    root.mainloop()
