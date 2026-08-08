"""
分析面板（Tkinter 组件）：胜率/目差曲线、AI 推荐、变化图（PV）、对局记录、复盘报告。
两个模式共用。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

import numpy as np


class AnalysisPanel:
    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.curve_type = "winrate"  # "winrate" | "scorelead"
        self.curve_data: List[tuple] = []  # [(move_no, value)]
        self.cands: List[dict] = []
        self.summary: Optional[dict] = None
        self.review_text = ""
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        f = ttk.LabelFrame(self.parent, text="AI 分析", padding=4)
        f.pack(fill="both", expand=True)

        # 推荐信息
        self.info_var = tk.StringVar(value="等待分析...")
        ttk.Label(f, textvariable=self.info_var, wraplength=240).pack(fill="x", pady=2)

        # 曲线切换
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.curve_btn = ttk.Button(row, text="📈 胜率曲线", width=12,
                                    command=self._toggle_curve)
        self.curve_btn.pack(side="left")
        ttk.Button(row, text="🔍 复盘报告", width=12, command=self._show_review).pack(side="left", padx=4)

        # 曲线画布
        self.canvas = tk.Canvas(f, width=280, height=120, bg="#1a1a2e",
                                highlightthickness=1, highlightbackground="#444")
        self.canvas.pack(fill="x", pady=4)

        # 变化图
        self.pv_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.pv_var, wraplength=280,
                  foreground="#cccccc").pack(fill="x")

    # ------------------------------------------------------------------
    def update_analysis(self, cands: List[dict], summary: dict, move_no: Optional[int] = None) -> None:
        """分析结果更新。move_no: 当前手数（曲线打点）。"""
        self.cands = cands
        self.summary = summary
        best = summary.get("best", "?")
        wr = summary.get("winrate", 0.5)
        lead = summary.get("scoreLead", 0.0)
        self.info_var.set(f"推荐 {best}   胜率 {wr*100:.0f}%   目差 {lead:+.1f}")
        pv = cands[0].get("pv", []) if cands else []
        self.pv_var.set("变化图: " + " → ".join(pv) if pv else "变化图: -")
        if move_no is not None:
            v = wr if self.curve_type == "winrate" else lead
            self.curve_data.append((move_no, v))
            self._draw_curve()

    def add_curve_point(self, move_no: int, winrate: float, score_lead: float) -> None:
        """手动打点（对局中每手结算）。"""
        v = winrate if self.curve_type == "winrate" else score_lead
        self.curve_data.append((move_no, v))
        self._draw_curve()

    def reset(self) -> None:
        self.curve_data = []
        self.cands = []
        self.summary = None
        self.info_var.set("等待分析...")
        self.pv_var.set("")
        self._draw_curve()

    # ------------------------------------------------------------------
    def _toggle_curve(self) -> None:
        self.curve_type = "scorelead" if self.curve_type == "winrate" else "winrate"
        self.curve_btn.config(text="📊 目差曲线" if self.curve_type == "winrate" else "📈 胜率曲线")
        self._draw_curve()

    def _draw_curve(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = int(c.cget("width")), int(c.cget("height"))
        data = self.curve_data
        if not data:
            c.create_text(w // 2, h // 2, text="暂无数据", fill="#888")
            return
        # 胜率：0-1 映射；目差：±15 映射
        if self.curve_type == "winrate":
            lo, hi = 0.0, 1.0
            label = "胜率"
        else:
            lo, hi = -15.0, 15.0
            label = "目差"
        xs = [d[0] for d in data]
        ys = [d[1] for d in data]
        x_min, x_max = min(xs), max(xs)
        # 目标线（胜率 0.5 / 目差 0）
        zero = h - (0.5 - lo) / (hi - lo) * (h - 20) - 10 if self.curve_type == "winrate" else \
            h - (0 - lo) / (hi - lo) * (h - 20) - 10
        c.create_line(0, zero, w, zero, fill="#555", dash=(4, 4))
        c.create_text(4, 6, text=label, fill="#aaa", anchor="nw")
        pts = []
        for (i, v) in data:
            px = 10 + (i - x_min) / max(1, (x_max - x_min)) * (w - 20)
            py = h - (v - lo) / (hi - lo) * (h - 20) - 10
            pts.append((px, py))
        if len(pts) == 1:
            x, y = pts[0]
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#00ff88")
        else:
            for k in range(len(pts) - 1):
                x1, y1 = pts[k]
                x2, y2 = pts[k + 1]
                c.create_line(x1, y1, x2, y2, fill="#00ff88", width=2)
        # 最新值
        lx, ly = pts[-1]
        c.create_oval(lx - 3, ly - 3, lx + 3, ly + 3, fill="#ff4444", outline="white")
        c.create_text(lx + 6, ly - 8, text=f"{ys[-1]:.0%}" if self.curve_type == "winrate"
                      else f"{ys[-1]:+.1f}", fill="#ff8888", anchor="w")

    def _show_review(self) -> None:
        if not self.review_text:
            self.review_text = "对局结束后自动生成复盘报告"
        top = tk.Toplevel(self.parent)
        top.title("AI 复盘报告")
        top.geometry("460x320")
        txt = tk.Text(top, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", self.review_text)
        txt.config(state="disabled")

    def set_review(self, text: str) -> None:
        self.review_text = text
