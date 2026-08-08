"""
透明置顶悬浮窗：叠加在围棋平台窗口上方，实时显示
- AI 推荐落点（闪烁圈 + "AI 推荐" 标签）
- 各候选点的实时胜率（圆点 + 百分比，胜率越高越红越大）
- 坐标开关（显示行/列标号）

透明方案：
- Windows：attributes -transparentcolor 把纯黑背景变为完全透明（只显示圆点/文字）
- 其他平台（Linux/mac 测试用）：退化为 -alpha 半透明黑底
"""
from __future__ import annotations

import sys
import tkinter as tk
from typing import List, Optional, Tuple

# 候选点颜色（胜率从低到高：蓝 → 绿 → 黄 → 红）
WR_COLORS = [
    (70, 130, 255),   # 蓝
    (80, 200, 120),   # 绿
    (255, 210, 60),   # 黄
    (255, 120, 60),   # 橙
    (255, 60, 60),    # 红
]


def _wr_color(winrate: float) -> str:
    """胜率 [0,1] → 颜色。"""
    t = max(0.0, min(1.0, winrate))
    idx = min(len(WR_COLORS) - 1, int(t * len(WR_COLORS)))
    r, g, b = WR_COLORS[idx]
    return f"#{r:02x}{g:02x}{b:02x}"


class BoardOverlay:
    """悬浮窗：与原棋盘同位置同尺寸的画布，透明背景只显示标记。"""

    def __init__(self, board, x: int, y: int, w: int, h: int,
                 show_coords: bool = True, always_on_top: bool = True):
        """
        board: BoardModel（交叉点 → 屏幕坐标）
        x, y, w, h: 窗口位置尺寸（与棋盘外框一致）
        """
        self.board = board
        self.show_coords = show_coords
        self.root = tk.Tk()
        self.root.overrideredirect(True)                # 无边框
        self.root.attributes("-topmost", always_on_top)  # 置顶
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        # 透明背景（Windows 真透明；其他平台半透明兜底）
        self._transparent = False
        try:
            self.root.attributes("-transparentcolor", "#000000")
            self._transparent = True
        except tk.TclError:
            try:
                self.root.attributes("-alpha", 0.30)
            except tk.TclError:
                pass
        self.canvas = tk.Canvas(self.root, width=w, height=h,
                                highlightthickness=0, bg="#000000")
        self.canvas.pack(fill="both", expand=True)
        # 鼠标穿透：悬浮窗不拦截点击（玩家在游戏窗口落子）
        self._enable_click_through()
        # 当前数据
        self._cands: List[dict] = []
        self._recommend: Optional[Tuple[int, int]] = None  # (x, y)
        self._flash = True
        self._flash_job = None
        self._start_flash()
        self._redraw()

    def _enable_click_through(self) -> None:
        """Windows：WS_EX_TRANSPARENT 让鼠标点击穿透悬浮窗落到游戏窗口。
        其他平台无系统级穿透（仅测试用，功能不受影响）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = self.root.winfo_id()
            # Tk 顶层窗口的实际 HWND 是 winfo_id 的父级
            top = ctypes.windll.user32.GetParent(hwnd)
            if not top:
                top = hwnd
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            ex = ctypes.windll.user32.GetWindowLongW(top, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                top, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass  # 穿透失败时悬浮窗会挡鼠标，用户可手动调整位置

    # ------------------------------------------------------------------
    def update(self, cands: List[dict], recommend: Optional[Tuple[int, int]] = None) -> None:
        """更新候选点（含胜率）与推荐落点。cands: [{move, winrate, ...}]。"""
        self._cands = cands or []
        self._recommend = recommend
        self._redraw()

    def set_show_coords(self, on: bool) -> None:
        self.show_coords = on
        self._redraw()

    # ------------------------------------------------------------------
    def _start_flash(self) -> None:
        try:
            self._flash_job = self.root.after(500, self._on_flash_tick)
        except Exception:
            pass

    def _on_flash_tick(self) -> None:
        self._flash = not self._flash
        self._redraw()
        self._start_flash()

    def _redraw(self) -> None:
        try:
            c = self.canvas
            c.delete("all")
            w = int(c.cget("width"))
            h = int(c.cget("height"))
            # 坐标标号（外框边缘，小字）
            if self.show_coords and len(self.board.corners) == 4:
                for i in range(self.board.size):
                    x, y = self.board.point_to_xy(i, 0)
                    c.create_text(x, 6, text=self.board.to_gtp(i, 0)[0],
                                  fill="#cccccc", font=("Arial", 7))
                    x, y = self.board.point_to_xy(0, i)
                    c.create_text(6, y, text=str(self.board.size - i),
                                  fill="#cccccc", font=("Arial", 7))
            # 候选点（圆点 + 胜率）
            for cand in self._cands:
                pt = self.board.from_gtp(cand.get("move", ""))
                if pt is None:
                    continue
                sx, sy = self.board.point_to_xy(*pt)
                wr = float(cand.get("winrate", 0.5))
                color = _wr_color(wr)
                r = 9 + int(wr * 14)  # 胜率越高越大
                c.create_oval(sx - r, sy - r, sx + r, sy + r,
                              fill=color, outline="white", width=1)
                c.create_text(sx, sy, text=f"{wr*100:.0f}",
                              fill="white", font=("Arial", 8, "bold"))
            # 推荐落点（闪烁圈）
            if self._recommend is not None:
                sx, sy = self.board.point_to_xy(*self._recommend)
                if self._flash:
                    c.create_oval(sx - 16, sy - 16, sx + 16, sy + 16,
                                  outline="#00ff88", width=3)
                    c.create_text(sx, sy - 24, text="AI 推荐",
                                  fill="#00ff88", font=("Arial", 9, "bold"))
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._flash_job:
                self.root.after_cancel(self._flash_job)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
