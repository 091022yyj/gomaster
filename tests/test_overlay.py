"""悬浮窗单元测试：画布坐标换算与胜率配色（不创建真实窗口）。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.board_recognition import BoardModel  # noqa: E402
from gomaster.overlay import _wr_color, canvas_xy  # noqa: E402


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

    def test_without_offset_markers_fall_outside_canvas(self, board):
        """回归：不减原点时标记整体偏移一个棋盘位置，几乎全被画布裁掉。"""
        wrong = board.point_to_xy(0, 0)
        assert wrong == (400.0, 300.0)
        assert wrong[0] > 180 and wrong[1] > 180  # 画布只有 180×180


class TestWinrateColor:
    def test_low_winrate_is_blue(self):
        assert _wr_color(0.0) == "#4682ff"

    def test_high_winrate_is_red(self):
        assert _wr_color(1.0) == "#ff3c3c"

    def test_clamps_out_of_range(self):
        assert _wr_color(-5.0) == _wr_color(0.0)
        assert _wr_color(99.0) == _wr_color(1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
