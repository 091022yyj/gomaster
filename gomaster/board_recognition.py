"""
GBR - Go Board Recognition
棋盘识别：自动检测棋盘外框（Canny 边缘 + 轮廓四边形）+ 霍夫圆检测棋子 +
交叉点归一到 19 路网格 → 输出局面数组（1=黑 -1=白 0=空）与 GTP 坐标转换。

设计目标：平台无关（腾讯围棋/野狐围棋通用），支持自动检测与手动校准两种方式。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

GTP_COLS = "abcdefghjklmnopqrstuvwxyz"  # 跳过 i


@dataclass
class BoardModel:
    """棋盘模型：由 4 个角点（图像坐标）定义的 19 路网格。"""

    size: int = 19
    # 角点顺序：左上、右上、右下、左下
    corners: List[Tuple[float, float]] = field(default_factory=list)

    def cell_size(self) -> float:
        if len(self.corners) < 4:
            return 0.0
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = self.corners
        # 网格间距 = 上边 / (size-1) 与 左边 / (size-1) 的平均
        top = np.hypot(x1 - x0, y1 - y0)
        left = np.hypot(x3 - x0, y3 - y0)
        return (top + left) / 2.0 / (self.size - 1)

    def point_to_xy(self, x: int, y: int) -> Tuple[float, float]:
        """交叉点 (x, y)（x 列向右，y 行向下）→ 图像坐标（双线性插值）。"""
        if len(self.corners) < 4:
            raise ValueError("棋盘未校准")
        u = x / (self.size - 1)
        v = y / (self.size - 1)
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = self.corners
        top_x = x0 + (x1 - x0) * u
        top_y = y0 + (y1 - y0) * u
        bot_x = x3 + (x2 - x3) * u
        bot_y = y3 + (y2 - y3) * u
        return top_x + (bot_x - top_x) * v, top_y + (bot_y - top_y) * v

    def xy_to_point(self, px: float, py: float) -> Optional[Tuple[int, int]]:
        """图像坐标 → 最近交叉点；超出棋盘范围返回 None。"""
        if len(self.corners) < 4:
            return None
        best: Optional[Tuple[int, int]] = None
        best_d = float("inf")
        for y in range(self.size):
            for x in range(self.size):
                cx, cy = self.point_to_xy(x, y)
                d = (cx - px) ** 2 + (cy - py) ** 2
                if d < best_d:
                    best_d = d
                    best = (x, y)
        # 超过半格距离视为棋盘外
        half = self.cell_size() / 2.0
        if best_d > half * half * 1.2:
            return None
        return best

    def to_gtp(self, x: int, y: int) -> str:
        """交叉点 → GTP 坐标（如 Q16，大写）。"""
        return GTP_COLS[x].upper() + str(self.size - y)

    def from_gtp(self, s: str) -> Optional[Tuple[int, int]]:
        """GTP 坐标 → 交叉点。"""
        v = s.strip().lower()
        if not v or v == "pass" or v == "resign":
            return None
        x = GTP_COLS.find(v[0])
        if x < 0:
            return None
        try:
            row = int(v[1:])
        except ValueError:
            return None
        y = self.size - row
        if x < 0 or x >= self.size or y < 0 or y >= self.size:
            return None
        return x, y


# ---------------------------------------------------------------------------
# 自动检测棋盘外框：轮廓找最大四边形
# ---------------------------------------------------------------------------
def find_board_auto(image: np.ndarray) -> Optional[BoardModel]:
    """自动检测棋盘外框。

    优先用 HSV 木色过滤定位（参考实现思路，抗干扰强）；
    失败则回退 Canny 边缘 + 最大四边形轮廓。
    """
    bgr = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    # 方法一：HSV 木色过滤 → 最大轮廓 → 四边形
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([10, 0, 0]), np.array([40, 255, 255]))
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    img_h, img_w = bgr.shape[:2]
    min_area = img_w * img_h * 0.05
    best: Optional[BoardModel] = None
    best_area = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        if area > best_area:
            best_area = area
            best = BoardModel(size=19, corners=_order_corners(approx.reshape(4, 2).astype(float)))
    if best is not None:
        return best
    # 方法二：Canny 边缘 + 最大四边形轮廓
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        if area > best_area:
            best_area = area
            best = BoardModel(size=19, corners=_order_corners(approx.reshape(4, 2).astype(float)))
    return best


def _order_corners(pts: np.ndarray) -> List[Tuple[float, float]]:
    """把 4 点按 左上、右上、右下、左下 排序。"""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return [tuple(tl), tuple(tr), tuple(br), tuple(bl)]


# ---------------------------------------------------------------------------
# 棋子识别：霍夫圆检测 + 颜色分类 → 局面数组
# ---------------------------------------------------------------------------
def recognize_stones(image: np.ndarray, board: BoardModel) -> np.ndarray:
    """识别棋盘内的棋子，返回 size×size 局面数组（1 黑 -1 白 0 空）。

    参考实现思路（更稳）：
    - 透视变换把棋盘拉正到固定尺寸
    - 每个交叉点取小窗口，统计暗像素占比（黑子）/亮像素占比（白子）
    """
    state = np.zeros((board.size, board.size), dtype=int)
    if len(board.corners) < 4:
        return state

    bgr = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 透视变换拉正棋盘（输出尺寸 = 19 格）
    S = 722
    src = np.array(board.corners, dtype="float32")
    dst = np.array([[0, 0], [S - 1, 0], [S - 1, S - 1], [0, S - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(gray, M, (S, S))

    cell = S / (board.size - 1)
    win = max(8, int(cell * 0.72))  # 采样窗口（交叉点周围）
    half = win // 2
    # 自适应阈值：以棋盘整体亮度为背景参考（不同平台木色深浅不同）
    bg = float(np.median(warped))
    dark_th_val = bg - 60
    light_th_val = bg + 20
    dark_th = 0.30   # 窗口内暗像素占比超过此值 = 黑子
    light_th = 0.25  # 亮像素占比超过此值 = 白子

    for y in range(board.size):
        for x in range(board.size):
            cx = int(round(x * cell))
            cy = int(round(y * cell))
            x0 = max(0, cx - half)
            x1 = min(S, cx + half + 1)
            y0 = max(0, cy - half)
            y1 = min(S, cy + half + 1)
            win_img = warped[y0:y1, x0:x1]
            if win_img.size == 0:
                continue
            dark = float(np.sum(win_img < dark_th_val)) / win_img.size
            light = float(np.sum(win_img > light_th_val)) / win_img.size
            if dark > dark_th:
                state[y, x] = 1
            elif light > light_th:
                state[y, x] = -1
    return state


def state_to_string(state: np.ndarray) -> str:
    """局面数组 → 多行字符串（调试/显示用）。B=黑 W=白 .=空。"""
    lines = []
    for row in state:
        lines.append("".join("B" if c == 1 else "W" if c == -1 else "." for c in row))
    return "\n".join(lines)


def board_to_history(state: np.ndarray) -> List[Tuple[int, int]]:
    """局面数组 → 着法列表（按行扫描，供引擎 play 同步）。"""
    moves = []
    for y in range(state.shape[0]):
        for x in range(state.shape[1]):
            if state[y, x] != 0:
                moves.append((state[y, x], x, y))
    return moves


# ---------------------------------------------------------------------------
# 测试辅助：合成一张围棋棋盘图像
# ---------------------------------------------------------------------------
def render_synthetic_board(size: int = 19, stones: Optional[List[Tuple[int, int, int]]] = None,
                           cell: int = 30, margin: int = 25) -> np.ndarray:
    """生成合成棋盘图像（白底网格 + 黑/白圆棋子），用于单元测试。

    stones: [(player, x, y)]  player=1 黑 -1 白
    """
    stones = stones or []
    w = margin * 2 + (size - 1) * cell
    img = np.full((w, w, 3), (230, 225, 210), dtype=np.uint8)  # 木色底
    for i in range(size):
        p = margin + i * cell
        cv2.line(img, (margin, p), (w - margin, p), (60, 50, 40), 1)
        cv2.line(img, (p, margin), (p, w - margin), (60, 50, 40), 1)
    for player, x, y in stones:
        cx = margin + x * cell
        cy = margin + y * cell
        color = (30, 30, 30) if player == 1 else (245, 245, 245)
        cv2.circle(img, (cx, cy), int(cell * 0.42), color, -1)
        cv2.circle(img, (cx, cy), int(cell * 0.42), (80, 70, 60), 1)
    return img
