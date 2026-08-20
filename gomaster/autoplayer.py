"""
自动落子：把棋盘交叉点换算成屏幕坐标并模拟鼠标点击。
平台无关（腾讯围棋 / 野狐围棋 / 任意窗口棋盘）。

坐标换算：截图取自某一块屏，图像原点是该屏左上角，而鼠标坐标是全局的
（macOS 副屏常在负坐标）。因此 屏幕点 = 屏幕原点 + 图像坐标 / 缩放。

落子前回读光标位置校验：跨显示器移动实测会偏，围棋里点错一格即下错一手，
校验不通过宁可不点，交由上层提示用户手动落子。
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

from .board_recognition import BoardModel

try:
    import pyautogui
    _HAS_PYAUTOGUI = True
except Exception:  # 无显示器/未安装 → 禁用自动点击（仅提示）
    _HAS_PYAUTOGUI = False

MOVE_TOLERANCE = 2.0  # 光标落点允许偏差（逻辑点）
MOVE_RETRIES = 3


def cursor_board_point(board: Optional[BoardModel], origin: Tuple[int, int] = (0, 0),
                       scale: float = 1.0) -> Optional[Tuple[int, int]]:
    """光标当前压住的交叉点；取不到光标或光标不在盘上时返回 None。

    对局平台会在光标下画一个"待落子"指示块，颜色随执棋方变化，
    recognize_stones 会把它当成真子 —— 识别时必须跳过这个点。
    """
    if not _HAS_PYAUTOGUI or board is None or len(board.corners) < 4:
        return None
    try:
        pos = pyautogui.position()
        ox, oy = origin
        return board.xy_to_point((pos.x - ox) * scale, (pos.y - oy) * scale)
    except Exception:
        return None


class AutoPlayer:
    def __init__(self, click_delay: float = 0.4, origin: Tuple[int, int] = (0, 0),
                 scale: float = 1.0, double_click: bool = False):
        self.click_delay = click_delay
        self.origin = origin
        self.scale = scale or 1.0
        self.double_click = double_click
        self.last_error = ""

    @staticmethod
    def available() -> bool:
        return _HAS_PYAUTOGUI

    def to_screen(self, ix: float, iy: float) -> Tuple[float, float]:
        """图像坐标 → 全局屏幕坐标（逻辑点）。"""
        ox, oy = self.origin
        return ox + ix / self.scale, oy + iy / self.scale

    def _move_verified(self, sx: float, sy: float) -> bool:
        """移动光标并回读校验，成功返回 True。"""
        for _ in range(MOVE_RETRIES):
            pyautogui.moveTo(sx, sy)
            time.sleep(0.06)
            pos = pyautogui.position()
            if abs(pos.x - sx) <= MOVE_TOLERANCE and abs(pos.y - sy) <= MOVE_TOLERANCE:
                return True
        self.last_error = (
            f"光标无法到达 ({sx:.0f},{sy:.0f})，停在 ({pos.x},{pos.y})；"
            "若始终原地不动，多半是缺少辅助功能（Accessibility）授权"
        )
        return False

    def click_point(self, board: BoardModel, x: int, y: int) -> Optional[Tuple[float, float]]:
        """在交叉点 (x, y) 处模拟点击；坐标校验失败返回 None（不点击）。"""
        if not _HAS_PYAUTOGUI:
            self.last_error = "未安装 pyautogui"
            return None
        try:
            self.last_error = ""
            sx, sy = self.to_screen(*board.point_to_xy(x, y))
            if not self._move_verified(sx, sy):
                return None
            pyautogui.click()
            if self.double_click:
                time.sleep(0.05)
                pyautogui.click()
            time.sleep(self.click_delay)
            return (sx, sy)
        except Exception as e:
            self.last_error = str(e)
            return None
