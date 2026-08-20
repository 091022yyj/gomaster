"""悬浮窗单元测试：画布坐标换算，以及标记不会被识别成棋子。"""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.board_recognition import BoardModel  # noqa: E402
from gomaster.overlay import (  # noqa: E402
    MARKER_COLOR,
    MARKER_RADIUS_CELLS,
    MARKER_WIDTH,
    canvas_xy,
)

# 与 recognize_stones 保持一致
SAMPLE_WINDOW_CELLS = 0.72
DARK_OFFSET = 60
LIGHT_OFFSET = 20


@pytest.fixture
def board():
    """棋盘在整屏图像的 (400,300)，19 路，格距 10px。"""
    return BoardModel(19, [(400, 300), (580, 300), (580, 480), (400, 480)])


class TestCanvasXY:
    """悬浮窗盖在棋盘上，画布原点是棋盘左上角，而 point_to_xy 给的是整屏坐标。"""

    def test_top_left_maps_to_canvas_origin(self, board):
        assert canvas_xy(board, (400, 300), 0, 0) == (0.0, 0.0)

    def test_bottom_right_maps_to_canvas_extent(self, board):
        assert canvas_xy(board, (400, 300), 18, 18) == (180.0, 180.0)

    def test_center_maps_to_canvas_center(self, board):
        assert canvas_xy(board, (400, 300), 9, 9) == (90.0, 90.0)


class TestMarkerNotMistakenForStone:
    """回归：填充的红色候选点被当成黑子同步进引擎，胜率越高越红、越红越像黑子。

    实测红色标记灰度 118，低于黑子阈值 bg-60=143，一个圆点就是一颗假黑子。
    """

    @pytest.mark.parametrize("cell", [20.0, 41.5, 60.0])
    def test_ring_falls_outside_sampling_window(self, cell):
        """采样窗是边长 cell*0.72 的方块，圆环内边必须在它的角点之外。"""
        half = max(8, int(cell * SAMPLE_WINDOW_CELLS)) // 2
        corner = half * np.sqrt(2)
        inner_edge = cell * MARKER_RADIUS_CELLS - MARKER_WIDTH / 2
        assert inner_edge > corner

    def test_marker_color_counts_as_neither_dark_nor_light(self):
        """第二重保险：标记灰度落在暗、亮两个阈值之间，两边都不计数。"""
        rgb = MARKER_COLOR.lstrip("#")
        bgr = np.array([[[int(rgb[4:6], 16), int(rgb[2:4], 16), int(rgb[0:2], 16)]]],
                       dtype=np.uint8)
        gray = int(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[0, 0])
        bg = 203  # 实测腾讯围棋棋盘的背景中位亮度
        assert bg - DARK_OFFSET < gray < bg + LIGHT_OFFSET

    def test_pure_red_would_have_been_mistaken_for_black(self):
        """反证：换成原来的红色就会掉进黑子区间。"""
        red = np.array([[[60, 60, 255]]], dtype=np.uint8)  # BGR
        gray = int(cv2.cvtColor(red, cv2.COLOR_BGR2GRAY)[0, 0])
        assert gray < 203 - DARK_OFFSET


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
