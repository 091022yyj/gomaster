"""棋盘识别单元测试：合成棋盘图像 → 自动检测/棋子识别/坐标转换。"""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.board_recognition import (  # noqa: E402
    BoardModel,
    _evenly_spaced,
    _trim_edge_artifacts,
    find_board_auto,
    recognize_stones,
    render_synthetic_board,
    state_to_string,
)


def make_board(stones=None, cell=30):
    img = render_synthetic_board(19, stones or [], cell=cell)
    return img


class TestBoardModel:
    def test_point_xy_roundtrip(self):
        board = BoardModel(size=19, corners=[(25, 25), (565, 25), (565, 565), (25, 565)])
        for x, y in [(0, 0), (9, 9), (18, 18), (3, 15)]:
            px, py = board.point_to_xy(x, y)
            assert board.xy_to_point(px, py) == (x, y)

    def test_gtp_conversion(self):
        board = BoardModel(size=19, corners=[(0, 0), (100, 0), (100, 100), (0, 100)])
        assert board.to_gtp(3, 15) == "D4"
        assert board.to_gtp(15, 3) == "Q16"
        assert board.from_gtp("D4") == (3, 15)
        assert board.from_gtp("Q16") == (15, 3)
        assert board.from_gtp("pass") is None
        assert board.from_gtp("I4") is None  # 无 i 列
        assert board.from_gtp("Z99") is None

    def test_xy_to_point_outside(self):
        board = BoardModel(size=19, corners=[(25, 25), (565, 25), (565, 565), (25, 565)])
        assert board.xy_to_point(10, 10) is None  # 棋盘外


class TestFindBoardAuto:
    def test_detect_synthetic(self):
        img = make_board()
        board = find_board_auto(img)
        assert board is not None
        # 角点应接近合成棋盘外框（margin=25, 尺寸 25+18*30+25=590）
        tl = board.corners[0]
        assert abs(tl[0] - 25) < 8 and abs(tl[1] - 25) < 8

    def test_corners_are_grid_not_wood_frame(self):
        """角点必须是最外圈线的交点：取成木框会让每点系统性偏移，边路整列错位。"""
        board = find_board_auto(render_synthetic_board(19, [], cell=30, margin=40))
        assert board is not None
        (x0, y0), _, (x1, y1), _ = board.corners
        assert abs(x0 - 40) <= 2 and abs(y0 - 40) <= 2
        assert abs(x1 - (40 + 18 * 30)) <= 2 and abs(y1 - (40 + 18 * 30)) <= 2
        assert board.cell_size() == pytest.approx(30.0, abs=0.5)

    @pytest.mark.parametrize("size", [9, 13, 19])
    def test_detects_board_size(self, size):
        board = find_board_auto(render_synthetic_board(size, [], cell=30, margin=40))
        assert board is not None and board.size == size

    def test_rejects_size_mismatch(self):
        """13 路残局不该被当成 19 路盘。"""
        img = render_synthetic_board(13, [], cell=30, margin=40)
        assert find_board_auto(img, size=13) is not None
        assert find_board_auto(img, size=19) is None

    def test_none_when_no_board(self):
        assert find_board_auto(np.full((400, 400, 3), 255, dtype=np.uint8)) is None

    def test_stones_do_not_break_detection(self):
        stones = [(1, x, y) for x in range(3, 9) for y in range(3, 9)]
        board = find_board_auto(render_synthetic_board(19, stones, cell=30, margin=40))
        assert board is not None and board.size == 19


class TestTrimEdgeArtifacts:
    """棋盘区域自身的边框会在投影上形成一条假网格线（实测 19 路数出 20 条）。"""

    def test_drops_leading_frame_line(self):
        # 取自真实截图：第 0 条是区域边框，真正首线在 53
        positions = [0, 53, 89, 124, 160, 195, 231, 266, 302]
        assert _trim_edge_artifacts(positions)[0] == 53

    def test_drops_trailing_frame_line(self):
        positions = [10, 45, 80, 115, 150, 240]
        assert _trim_edge_artifacts(positions)[-1] == 150

    def test_keeps_clean_lattice(self):
        positions = [10, 40, 70, 100, 130]
        assert _trim_edge_artifacts(positions) == positions

    def test_evenly_spaced_rejects_irregular(self):
        assert _evenly_spaced([0, 30, 60, 90]) is True
        assert _evenly_spaced([0, 5, 60, 90]) is False


class TestRecognizeStones:
    def test_recognize_simple(self):
        stones = [(1, 4, 4), (-1, 3, 3), (1, 15, 3)]
        img = make_board(stones)
        board = find_board_auto(img)
        assert board is not None
        state = recognize_stones(img, board)
        assert state[4, 4] == 1
        assert state[3, 3] == -1
        assert state[3, 15] == 1
        assert state[0, 0] == 0

    def test_state_to_string(self):
        state = np.zeros((19, 19), dtype=int)
        state[0, 0] = 1
        state[1, 1] = -1
        s = state_to_string(state)
        assert s.split("\n")[0].startswith("B")
        assert s.split("\n")[1][1] == "W"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
