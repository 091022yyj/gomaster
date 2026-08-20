"""
透明置顶悬浮窗：叠加在围棋平台窗口上方，只标出 AI 推荐的下一手。

标记必须画得让识别采不到，否则会被当成真棋子同步进引擎、把胜率越推越高、
越高越红、越红越像黑子——形成自我投毒的死循环（实测红色标记灰度 118，
低于黑子阈值 143，一个候选点圆点就被认成一颗黑子）。因此：
- 只画细圆环，不填充，半径大于采样窗（cell*0.72 的方块）
- 交叉点上不写任何文字
- 环的颜色取灰度落在"既不够暗也不够亮"的区间，作为第二重保险

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
MARKER_COLOR = "#00ff88"     # 灰度约 165，落在暗阈值 143 与亮阈值 223 之间
MARKER_RADIUS_CELLS = 0.62   # 采样窗半对角最大约 0.5 格，环画在它外面
MARKER_WIDTH = 2


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
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        bg = self._apply_transparency()
        self.canvas = tk.Canvas(self.root, width=w, height=h,
                                highlightthickness=0, bg=bg)
        self.canvas.pack(fill="both", expand=True)
        self.root.update_idletasks()
        # 置顶必须在窗口映射之后：map 之前设 -topmost，macOS 上 NSWindow.level
        # 会停在 0（实测 map 前设=0 / map 后设=19），窗口根本没抬起来
        self.root.attributes("-topmost", always_on_top)
        self.root.update_idletasks()
        self.window_number = self._setup_native(w, h)
        # 当前数据
        self._cands: List[dict] = []
        self._recommend: Optional[Tuple[int, int]] = None  # (x, y)
        self._flash = True
        self._flash_job = None
        self._closed = False
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

    def _setup_native(self, w: int, h: int) -> Optional[int]:
        """macOS 原生窗口设置：点击穿透 + 返回窗口号（供截图排除自身）。

        窗口号只在**确认已置顶**时才返回。截图用的
        kCGWindowListOptionOnScreenBelowWindow 会连同该窗口上方的一切一起排除，
        若悬浮窗没抬起来，用户点一下对局窗口就会把游戏本身排出画面，
        识别到的将是桌面壁纸——比悬浮窗入镜严重得多。
        """
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
            return None
        if sys.platform != "darwin":
            return None
        try:
            from AppKit import NSApp

            for win in NSApp().windows():
                frame = win.frame()
                if (win.isVisible() and abs(frame.size.width - w) < 2
                        and abs(frame.size.height - h) < 2):
                    win.setIgnoresMouseEvents_(True)
                    return int(win.windowNumber()) if win.level() > 0 else None
        except Exception:
            pass
        return None

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
            self.canvas.delete("all")
            if self._recommend is None or not self._flash:
                return
            sx, sy = canvas_xy(self.board, self._origin, *self._recommend)
            r = self.board.cell_size() * MARKER_RADIUS_CELLS
            self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r,
                                    outline=MARKER_COLOR, width=MARKER_WIDTH)
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
