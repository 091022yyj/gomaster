"""
Tkinter 主界面（双模式）：
- 手动模式：识别屏幕棋盘 → 悬浮窗显示 AI 推荐落点 + 各候选点实时胜率，玩家自己落子
- 全自动模式：识别屏幕棋盘 → AI 自动点击落子
共用：分析面板（胜率/目差曲线、变化图、复盘报告）、对局记录、战绩、SGF 导出。
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

import numpy as np

from .board_recognition import BoardModel, find_board_auto, recognize_stones, state_to_string, _order_corners
from .capture import PRIMARY, Monitor, grab_screen, list_monitors
from .config import Config
from .history import export_sgf, list_games, save_game, stats
from .manual_mode import ManualMode
from .main_loop import GoMasterLoop
from .overlay import BoardOverlay
from .panel import AnalysisPanel

MAX_PREVIEW_W = 480
MAX_PREVIEW_H = 380


class GomasterGUI:
    def __init__(self, root: tk.Tk, config: Config):
        self.root = root
        self.cfg = config
        self.mode = "manual"  # "manual" | "auto"
        self.manual: Optional[ManualMode] = None
        self.loop: Optional[GoMasterLoop] = None
        self.corners: List[Tuple[float, float]] = []
        self.preview_img = None  # 当前截图（全分辨率）
        self.preview_scale = 1.0
        self.game_moves: List[tuple] = []  # [(player, x, y)]
        self.move_count = 0
        self.my_color: Optional[str] = None

        root.title("GoMaster - AI 围棋助手（手动 / 全自动）")

        self._build_ui()
        self._fit_window()
        self._refresh_preview()

    def _fit_window(self) -> None:
        """按内容实际需要开窗，并压进屏幕可视范围。

        Tk 在 macOS 上行高比 Windows 大，写死 1180x700 会把底部控制栏顶出屏幕外。
        """
        self.root.update_idletasks()
        w = min(max(self.root.winfo_reqwidth(), 1180), self.root.winfo_screenwidth() - 40)
        h = min(self.root.winfo_reqheight(), self.root.winfo_screenheight() - 120)
        self.root.geometry(f"{w}x{h}+40+40")

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        # 模式选择
        row = ttk.Frame(top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="模式:").pack(side="left")
        self.var_mode = tk.StringVar(value="manual")
        ttk.Radiobutton(row, text="🖐 手动（悬浮窗提示，自己落子）", value="manual",
                        variable=self.var_mode, command=self._on_mode_change).pack(side="left", padx=4)
        ttk.Radiobutton(row, text="🤖 全自动（AI 自动点击落子）", value="auto",
                        variable=self.var_mode, command=self._on_mode_change).pack(side="left", padx=4)

        # 引擎设置
        row = ttk.Frame(top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="KataGo 路径:").pack(side="left")
        self.var_katago = tk.StringVar(value=self.cfg.katago_path)
        ttk.Entry(row, textvariable=self.var_katago, width=34).pack(side="left", padx=4)
        ttk.Button(row, text="浏览", command=self._pick_katago).pack(side="left")

        row = ttk.Frame(top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="模型路径:").pack(side="left")
        self.var_model = tk.StringVar(value=self.cfg.model_path)
        ttk.Entry(row, textvariable=self.var_model, width=34).pack(side="left", padx=4)
        ttk.Button(row, text="浏览", command=self._pick_model).pack(side="left")

        row = ttk.Frame(top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="思考秒数:").pack(side="left")
        self.var_think = tk.StringVar(value=str(self.cfg.think_seconds))
        ttk.Spinbox(row, from_=1, to=60, textvariable=self.var_think, width=5).pack(side="left", padx=4)
        ttk.Label(row, text="轮询(s):").pack(side="left")
        self.var_interval = tk.StringVar(value=str(self.cfg.interval))
        ttk.Spinbox(row, from_=0.2, to=10, increment=0.2,
                    textvariable=self.var_interval, width=5).pack(side="left", padx=4)
        self.var_coords = tk.BooleanVar(value=self.cfg.overlay_coords)
        ttk.Checkbutton(row, text="悬浮窗坐标", variable=self.var_coords,
                        command=self._on_coords_toggle).pack(side="left", padx=8)
        self.var_sound = tk.BooleanVar(value=self.cfg.sound)
        ttk.Checkbutton(row, text="提示音", variable=self.var_sound).pack(side="left", padx=8)

        row = ttk.Frame(top)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="我执:").pack(side="left")
        self.var_color = tk.StringVar(value=self.cfg.my_color)
        for text, value in (("自动判断", "auto"), ("● 黑", "B"), ("○ 白", "W")):
            ttk.Radiobutton(row, text=text, value=value,
                            variable=self.var_color).pack(side="left", padx=2)
        ttk.Label(row, text="   识别屏幕:").pack(side="left")
        self._monitors = list_monitors()
        self.var_monitor = tk.StringVar()
        combo = ttk.Combobox(row, textvariable=self.var_monitor, width=34, state="readonly",
                             values=[m.label() for m in self._monitors])
        combo.pack(side="left", padx=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_preview())
        for i, m in enumerate(self._monitors):
            if m.index == self.cfg.monitor:
                combo.current(i)
                break
        else:
            if self._monitors:
                combo.current(0)
        ttk.Label(row, text="（对局窗口放哪块屏就选哪块）").pack(side="left")

        # 底部控制栏先 pack 并锚到底：空间不够时被压缩的应是预览区而非按钮
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(side="bottom", fill="x")

        # 主区域：预览 + 分析面板
        mid = ttk.Frame(self.root, padding=8)
        mid.pack(fill="both", expand=True)

        left = ttk.LabelFrame(mid, text="屏幕截图（点击棋盘 4 角校准：左上→右上→右下→左下）", padding=4)
        left.pack(side="left", fill="both", expand=True)
        self.preview_canvas = tk.Canvas(left, width=MAX_PREVIEW_W, height=MAX_PREVIEW_H,
                                        bg="#222", cursor="crosshair")
        self.preview_canvas.pack()
        self.preview_canvas.bind("<Button-1>", self._on_preview_click)

        right = ttk.Frame(mid)
        right.pack(side="right", fill="y")
        self.panel = AnalysisPanel(right)

        # 底部：日志 + 控制
        self.log = tk.Text(bottom, height=7, state="disabled")
        self.log.pack(fill="x")

        ctrl = ttk.Frame(bottom)
        ctrl.pack(fill="x", pady=4)
        ttk.Button(ctrl, text="📷 刷新截图", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Button(ctrl, text="🎯 自动检测棋盘", command=self._auto_detect).pack(side="left", padx=4)
        ttk.Button(ctrl, text="✓ 校准完成", command=self._apply_board).pack(side="left", padx=4)
        ttk.Button(ctrl, text="💾 保存配置", command=self._save_config).pack(side="left", padx=4)
        self.btn_start = ttk.Button(ctrl, text="▶ 开始", command=self._toggle_start)
        self.btn_start.pack(side="left", padx=4)
        ttk.Button(ctrl, text="⏹ 停止", command=self._stop).pack(side="left", padx=4)
        ttk.Button(ctrl, text="📥 导出 SGF", command=self._export_sgf).pack(side="left", padx=4)
        ttk.Button(ctrl, text="🏆 战绩", command=self._show_stats).pack(side="left", padx=4)

    # ------------------------------------------------------------------
    def _on_mode_change(self) -> None:
        self.mode = self.var_mode.get()
        self._log(f"模式切换为: {'手动' if self.mode == 'manual' else '全自动'}")

    def _on_coords_toggle(self) -> None:
        self.cfg.overlay_coords = self.var_coords.get()
        if self.manual and self.manual.overlay:
            self.manual.overlay.set_show_coords(self.cfg.overlay_coords)

    def _pick_katago(self) -> None:
        p = filedialog.askopenfilename(title="选择 katago.exe / katago")
        if p:
            self.var_katago.set(p)

    def _pick_model(self) -> None:
        p = filedialog.askopenfilename(title="选择模型文件 model.bin.gz")
        if p:
            self.var_model.set(p)

    def _read_cfg(self) -> Config:
        self.cfg.katago_path = self.var_katago.get().strip()
        self.cfg.model_path = self.var_model.get().strip()
        try:
            self.cfg.think_seconds = float(self.var_think.get())
            self.cfg.interval = float(self.var_interval.get())
        except ValueError:
            pass
        self.cfg.overlay_coords = self.var_coords.get()
        self.cfg.sound = self.var_sound.get()
        self.cfg.monitor = self._selected_monitor().index
        self.cfg.my_color = self.var_color.get()
        return self.cfg

    def _selected_monitor(self) -> Monitor:
        label = self.var_monitor.get()
        for m in self._monitors:
            if m.label() == label:
                return m
        return self._monitors[0] if self._monitors else Monitor(PRIMARY, 0, 0, 0, 0)

    def _save_config(self) -> None:
        self._read_cfg().save()
        self._log("配置已保存")

    # ------------------------------------------------------------------
    def _refresh_preview(self) -> None:
        img = grab_screen(self._selected_monitor().index)
        if img is None:
            self._log("截图失败：请确认已安装 mss（pip install mss）且非无头环境")
            return
        self.preview_img = img
        self.corners = []
        self._draw_preview()

    def _draw_preview(self) -> None:
        if self.preview_img is None:
            return
        h, w = self.preview_img.shape[:2]
        scale = min(MAX_PREVIEW_W / w, MAX_PREVIEW_H / h, 1.0)
        self.preview_scale = scale
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        from PIL import Image, ImageTk
        rgb = self.preview_img[:, :, ::-1]  # BGR → RGB
        img = Image.fromarray(rgb)
        img = img.resize((nw, nh), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, anchor="nw", image=self._photo)
        for i, (x, y) in enumerate(self.corners):
            sx, sy = x * scale, y * scale
            self.preview_canvas.create_oval(sx - 5, sy - 5, sx + 5, sy + 5,
                                            outline="#ff4444", width=2)
            self.preview_canvas.create_text(sx + 8, sy - 8, text=str(i + 1),
                                            fill="#ff4444", anchor="w")

    def _on_preview_click(self, event) -> None:
        if self.preview_img is None:
            return
        x = event.x / self.preview_scale
        y = event.y / self.preview_scale
        if len(self.corners) >= 4:
            self.corners = []
        self.corners.append((x, y))
        self._draw_preview()
        if len(self.corners) == 4:
            self._log("4 个角已选好，点「✓ 校准完成」继续")

    def _auto_detect(self) -> None:
        if self.preview_img is None:
            self._refresh_preview()
            return
        board = find_board_auto(self.preview_img, size=self.cfg.board_size)
        if board is None:
            self._log("自动检测失败：请手动点击 4 个角校准")
            return
        self.corners = board.corners
        self._draw_preview()
        self._log("自动检测到棋盘外框 ✓（可微调后点校准完成）")

    def _apply_board(self) -> None:
        if len(self.corners) != 4:
            self._log("请先选择 4 个角点")
            return
        board = BoardModel(size=self.cfg.board_size,
                           corners=_order_corners(np.array(self.corners, dtype=float)))
        if self.preview_img is not None:
            state = recognize_stones(self.preview_img, board)
        if self.mode == "manual":
            self._ensure_manual().set_board(board)
        else:
            self._ensure_loop().set_board(board)
        self._log("棋盘校准完成 ✓")

    # ------------------------------------------------------------------
    def _make_overlay(self, board, x: int, y: int, w: int, h: int):
        """在主线程创建悬浮窗并回传（macOS 下子线程建 Tk 会直接 abort 进程）。"""
        def build():
            return BoardOverlay(board, x, y, w, h,
                                show_coords=self.cfg.overlay_coords, master=self.root)

        # 已在主线程就直接建：此时 after() 排的队要等本函数返回才轮到，等待必然超时
        if threading.current_thread() is threading.main_thread():
            return build()

        box: dict = {}
        done = threading.Event()

        def run() -> None:
            try:
                box["ov"] = build()
            except Exception as e:
                box["err"] = e
            finally:
                done.set()

        self.root.after(0, run)
        if not done.wait(timeout=5):
            raise RuntimeError("主线程未响应，悬浮窗创建超时")
        if "err" in box:
            raise box["err"]
        return box["ov"]

    def _ensure_manual(self) -> ManualMode:
        if self.manual is None:
            self.manual = ManualMode(
                self._read_cfg(),
                on_status=self._log,
                on_analysis=self._on_analysis,
                on_state=self._on_state,
                overlay_factory=self._make_overlay,
            )
        return self.manual

    def _ensure_loop(self) -> GoMasterLoop:
        if self.loop is None:
            self.loop = GoMasterLoop(
                self._read_cfg(),
                on_status=self._log,
                on_state=self._on_state,
            )
        return self.loop

    # ------------------------------------------------------------------
    def _on_analysis(self, cands: List[dict], summary: dict) -> None:
        """手动模式分析回调：更新面板（线程回调 → 主线程刷新）。"""
        self.move_count = max(self.move_count, len(self.game_moves) + 1)
        self._safe_panel(lambda: self.panel.update_analysis(cands, summary, self.move_count))

    def _on_state(self, state: np.ndarray) -> None:
        def _do():
            self._show_state(state)
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def _safe_panel(self, fn) -> None:
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    def _show_state(self, state: np.ndarray) -> None:
        # 局面文本显示在日志区上方？简化：不显示文本棋盘，保持干净
        pass

    def _log(self, msg: str) -> None:
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _toggle_start(self) -> None:
        cfg = self._read_cfg()
        if not cfg.katago_path or not cfg.model_path:
            messagebox.showwarning("提示", "请先填写 KataGo 引擎和模型路径")
            return
        if self.mode == "manual":
            if self.manual and self.manual._thread and self.manual._thread.is_alive():
                self._log("已在运行中")
                return
            self._ensure_manual().config = cfg
            self._log(f"开始（手动模式）：思考 {cfg.think_seconds}s")
            self.manual.start()
        else:
            if self.loop and self.loop._thread and self.loop._thread.is_alive():
                self._log("已在运行中")
                return
            self._ensure_loop().config = cfg
            self._log(f"开始（全自动模式）：思考 {cfg.think_seconds}s")
            self.loop.start()

    def _stop(self) -> None:
        if self.manual:
            self.manual.stop()
        if self.loop:
            self.loop.stop()
        self._log("已停止")

    def _export_sgf(self) -> None:
        moves = self.game_moves
        if self.manual and self.manual.game_moves:
            moves = self.manual.game_moves
        if not moves:
            self._log("无对局记录")
            return
        path = export_sgf([(p, x, y) for p, x, y, *_ in moves])
        self._log(f"SGF 已导出: {path}")

    def _show_stats(self) -> None:
        s = stats()
        games = list_games()
        msg = (f"总局数: {s['total']}\n"
               f"胜: {s['wins']}  负: {s['losses']}  和: {s['draws']}\n"
               f"胜率: {s['win_rate']*100:.0f}%\n\n最近对局:\n")
        for g in games[-5:]:
            msg += f"  {g['time']}  {len(g['moves'])} 手  {g.get('result') or ''}\n"
        messagebox.showinfo("战绩统计", msg)

    def close(self) -> None:
        if self.manual:
            self.manual.stop()
        if self.loop:
            self.loop.stop()
