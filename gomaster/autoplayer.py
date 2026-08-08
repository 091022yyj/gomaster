"""
自动落子：根据棋盘模型把 GTP 坐标换算成屏幕像素坐标并模拟鼠标点击。
平台无关（腾讯围棋 / 野狐围棋 / 任意窗口棋盘）。
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


class AutoPlayer:
    def __init__(self, click_delay: float = 0.4, double_click: bool = False):
        self.click_delay = click_delay
        self.double_click = double_click

    @staticmethod
    def available() -> bool:
        return _HAS_PYAUTOGUI

    def click_point(self, board: BoardModel, x: int, y: int) -> Optional[Tuple[float, float]]:
        """在交叉点 (x, y) 处模拟点击（屏幕坐标 = 截图坐标，全屏截图场景）。"""
        if not _HAS_PYAUTOGUI:
            return None
        try:
            sx, sy = board.point_to_xy(x, y)
            pyautogui.moveTo(sx, sy, duration=0.1)
            time.sleep(0.05)
            pyautogui.click()
            if self.double_click:
                time.sleep(0.05)
                pyautogui.click()
            time.sleep(self.click_delay)
            return (sx, sy)
        except Exception:
            return None
