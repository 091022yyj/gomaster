"""
透明置顶悬浮窗：叠加在围棋平台窗口上方，实时显示
- AI 推荐落点（闪烁圈 + "AI 推荐" 标签）
- 各候选点的实时胜率（圆点 + 百分比，胜率越高越红越大）
- 坐标开关（显示行/列标号）

透明与穿透按平台分流：
- Windows：-transparentcolor 把纯黑背景抠成全透明；WS_EX_TRANSPARENT 让点击穿透
- macOS：-transparent + systemTransparent 背景；NSWindow.ignoresMouseEvents 穿透
- 其他平台：-alpha 半透明兜底，无穿透

线程约定：macOS 的 Aqua 强制 Tk 只能在主线程操作（子线程建窗会直接 abort 进程），
因此构造必须发生在主线程，其余公开方法自行把绘制回送主线程。
"""
from __future__ import annotations

import sys
import threading
import tkinter as tk
from typing import List, Optional, Tuple

TRANSPARENT_KEY = "#000000"

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


def canvas_xy(board, origin: Tuple[int, int], x: int, y: int) -> Tuple[float, float]:
    """交叉点 → 画布坐标。

    board.point_to_xy 给的是整屏图像坐标，而画布原点在棋盘左上角，必须减掉，
    否则所有标记整体偏移一个棋盘位置，绝大部分被画布裁掉。
    """
    sx, sy = board.point_to_xy(x, y)
    return sx - origin[0], sy - origin[1]


class BoardOverlay:
    """悬浮窗：与原棋盘同位置同尺寸的画布，透明背景只显示标记。"""

    def __init__(self, board, x: int, y: int, w: int, h: int,
                 show_coords: bool = True, always_on_top: bool = True,
                 master: Optional[tk.Misc] = None):
        """
        board: BoardModel（交叉点 → 图像坐标，与悬浮窗左上角同原点）
        x, y, w, h: 窗口位置尺寸（与棋盘外框一致）
        master: 已有的 Tk 根窗口；缺省时自建（仅适用于独立运行/测试）
        """
        self.board = board
        self.show_coords = show_coords
        # 画布原点是棋盘左上角，而 point_to_xy 给的是整屏图像坐标，作图前要减掉
        self._origin = (x, y)
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        self.root.overrideredirect(True)                 # 无边框
        self.root.attributes("-topmost", always_on_top)  # 置顶
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        bg = self._apply_transparency()
        self.canvas = tk.Canvas(self.root, width=w, height=h,
                                highlightthickness=0, bg=bg)
        self.canvas.pack(fill="both", expand=True)
        self.root.update_idletasks()
        # 鼠标穿透：悬浮窗不拦截点击（玩家在游戏窗口落子）
        self._enable_click_through(w, h)
        # 当前数据
        self._cands: List[dict] = []
        self._recommend: Optional[Tuple[int, int]] = None  # (x, y)
        self._flash = True
        self._flash_job = None
        self._closed = False
        self.window_number: Optional[int] = self._find_window_number(w, h)
        self._start_flash()
        self._redraw()

    # ------------------------------------------------------------------
    def _apply_transparency(self) -> str:
        """按平台开启透明，返回画布应使用的背景色。"""
        if sys.platform == "win32":
            try:
                self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
                return TRANSPARENT_KEY
            except tk.TclError:
                pass
        elif sys.platform == "darwin":
            try:
                self.root.attributes("-transparent", True)
                return "systemTransparent"
            except tk.TclError:
                pass
        try:
            self.root.attributes("-alpha", 0.30)
        except tk.TclError:
            pass
        return TRANSPARENT_KEY

    def _find_ns_window(self, w: int, h: int):
        """按尺寸认出自己这个 Toplevel 对应的 NSWindow（macOS）。"""
        from AppKit import NSApp

        for win in NSApp().windows():
            frame = win.frame()
            if (win.isVisible() and abs(frame.size.width - w) < 2
                    and abs(frame.size.height - h) < 2):
                return win
        return None

    def _find_window_number(self, w: int, h: int) -> Optional[int]:
        """自己的窗口号，供截图时排除本窗口（见 capture._grab_below_window）。"""
        if sys.platform != "darwin":
            return None
        try:
            win = self._find_ns_window(w, h)
            return int(win.windowNumber()) if win is not None else None
        except Exception:
            return None

    def _enable_click_through(self, w: int, h: int) -> None:
        """让鼠标点击穿透悬浮窗落到游戏窗口；失败时悬浮窗会挡鼠标，可手动挪开。"""
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = self.root.winfo_id()
                # Tk 顶层窗口的实际 HWND 是 winfo_id 的父级
                top = ctypes.windll.user32.GetParent(hwnd) or hwnd
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                WS_EX_TRANSPARENT = 0x00000020
                ex = ctypes.windll.user32.GetWindowLongW(top, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(
                    top, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                win = self._find_ns_window(w, h)
                if win is not None:
                    win.setIgnoresMouseEvents_(True)
            except Exception:
                pass

    def _post(self, fn) -> None:
        """把 Tk 操作放到主线程执行（macOS 下跨线程操作 Tk 会 abort 进程）。"""
        if threading.current_thread() is threading.main_thread():
            fn()
            return
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def update(self, cands: List[dict], recommend: Optional[Tuple[int, int]] = None) -> None:
        """更新候选点（含胜率）与推荐落点。cands: [{move, winrate, ...}]。可跨线程调用。"""
        self._cands = cands or []
        self._recommend = recommend
        self._post(self._redraw)

    def set_show_coords(self, on: bool) -> None:
        self.show_coords = on
        self._post(self._redraw)

    # ------------------------------------------------------------------
    def _start_flash(self) -> None:
        try:
            self._flash_job = self.root.after(500, self._on_flash_tick)
        except Exception:
            pass

    def _on_flash_tick(self) -> None:
        if self._closed:
            return
        self._flash = not self._flash
        self._redraw()
        self._start_flash()

    def _redraw(self) -> None:
        try:
            c = self.canvas
            c.delete("all")
            # 坐标标号（外框边缘，小字）
            if self.show_coords and len(self.board.corners) == 4:
                for i in range(self.board.size):
                    x, _ = canvas_xy(self.board, self._origin, i, 0)
                    c.create_text(x, 6, text=self.board.to_gtp(i, 0)[0],
                                  fill="#cccccc", font=("Arial", 7))
                    _, y = canvas_xy(self.board, self._origin, 0, i)
                    c.create_text(6, y, text=str(self.board.size - i),
                                  fill="#cccccc", font=("Arial", 7))
            # 候选点（圆点 + 胜率）
            for cand in self._cands:
                pt = self.board.from_gtp(cand.get("move", ""))
                if pt is None:
                    continue
                sx, sy = canvas_xy(self.board, self._origin, *pt)
                wr = float(cand.get("winrate", 0.5))
                r = 9 + int(wr * 14)  # 胜率越高越大
                c.create_oval(sx - r, sy - r, sx + r, sy + r,
                              fill=_wr_color(wr), outline="white", width=1)
                c.create_text(sx, sy, text=f"{wr*100:.0f}",
                              fill="white", font=("Arial", 8, "bold"))
            # 推荐落点（闪烁圈）
            if self._recommend is not None and self._flash:
                sx, sy = canvas_xy(self.board, self._origin, *self._recommend)
                c.create_oval(sx - 16, sy - 16, sx + 16, sy + 16,
                              outline="#00ff88", width=3)
                c.create_text(sx, sy - 24, text="AI 推荐",
                              fill="#00ff88", font=("Arial", 9, "bold"))
        except Exception:
            pass

    def close(self) -> None:
        self._closed = True
        self._post(self._destroy)

    def _destroy(self) -> None:
        try:
            if self._flash_job:
                self.root.after_cancel(self._flash_job)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
