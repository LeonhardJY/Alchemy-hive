"""weflow-agent 桌面界面（Tkinter 薄壳，业务逻辑在 actions.py）。"""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .actions import run_pipeline
from ..core.distill import DistillError


class AgentGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("weflow-agent — 微信聊天 → buzz agent")
        root.geometry("640x560")
        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)

        # 聊天文件
        ttk.Label(frm, text="聊天文件（WeFlow 导出 JSON 或微信 txt）:").grid(row=0, column=0, sticky="w")
        self.chat_path = tk.StringVar()
        ttk.Entry(frm, textvariable=self.chat_path, width=40).grid(row=1, column=0, sticky="we")
        ttk.Button(frm, text="浏览…", command=self._pick_file).grid(row=1, column=1)

        # 人物名
        ttk.Label(frm, text="人物名（显示名）:").grid(row=2, column=0, sticky="w")
        self.name = tk.StringVar(value="张書源")
        ttk.Entry(frm, textvariable=self.name).grid(row=3, column=0, sticky="we")

        # 模型配置
        ttk.Label(frm, text="模型配置（LLM 必需）:").grid(row=4, column=0, sticky="w")
        ttk.Label(frm, text="base_url").grid(row=5, column=0, sticky="w")
        self.base_url = tk.StringVar(value="https://api.deepseek.com/v1")
        ttk.Entry(frm, textvariable=self.base_url).grid(row=6, column=0, sticky="we")
        ttk.Label(frm, text="api_key").grid(row=7, column=0, sticky="w")
        self.api_key = tk.StringVar()
        ttk.Entry(frm, textvariable=self.api_key, show="*").grid(row=8, column=0, sticky="we")
        ttk.Label(frm, text="model").grid(row=9, column=0, sticky="w")
        self.model = tk.StringVar(value="deepseek-chat")
        ttk.Entry(frm, textvariable=self.model).grid(row=10, column=0, sticky="we")

        # 运行按钮
        ttk.Button(frm, text="开始蒸馏（import → distill → export）", command=self._run).grid(row=11, column=0, columnspan=2, pady=8)

        # 日志区
        ttk.Label(frm, text="日志:").grid(row=12, column=0, sticky="w")
        self.log = scrolledtext.ScrolledText(frm, height=14, state="disabled", width=74)
        self.log.grid(row=13, column=0, columnspan=2, sticky="nsew")
        frm.rowconfigure(13, weight=1)
        frm.columnconfigure(0, weight=1)

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(title="选择聊天文件", filetypes=[("聊天文件", "*.json *.txt"), ("所有文件", "*.*")])
        if path:
            self.chat_path.set(path)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _run(self) -> None:
        model_config = {"base_url": self.base_url.get().strip(), "api_key": self.api_key.get().strip(), "model": self.model.get().strip()}
        try:
            logs = run_pipeline(self.chat_path.get().strip(), self.name.get().strip(), model_config, "build")
            for line in logs:
                self._append_log(line)
            self._append_log("完成 ✅ 可在 build/export/ 找到 .agent.json，拖入 buzz 桌面端导入。")
        except DistillError as e:
            self._append_log(f"错误: {e}")
            messagebox.showerror("蒸馏失败", str(e))
        except Exception as e:
            self._append_log(f"错误: {e}")
            messagebox.showerror("出错", str(e))


def run_gui() -> None:
    root = tk.Tk()
    AgentGUI(root)
    root.mainloop()
