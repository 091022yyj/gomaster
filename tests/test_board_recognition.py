"""棋盘识别单元测试：合成棋盘图像 → 自动检测/棋子识别/坐标转换。"""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.board_recognition import (  # noqa: E402
    BoardModel,
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
