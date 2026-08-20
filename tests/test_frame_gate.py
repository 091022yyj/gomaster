"""帧合理性闸门单元测试：挡掉整帧误识别与瞬时噪声。"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.board_recognition import FrameGate, plausible_position  # noqa: E402


def board_with(black=0, white=0):
    state = np.zeros((19, 19), dtype=int)
    flat = state.reshape(-1)
    flat[:black] = 1
    flat[black:black + white] = -1
    return state


class TestPlausiblePosition:
    def test_balanced_position_ok(self):
        assert plausible_position(board_with(black=40, white=39)) is True

    def test_handicap_still_ok(self):
        assert plausible_position(board_with(black=9, white=0)) is True

    def test_all_one_color_rejected(self):
        """截到壁纸时会整片判成同色（实测 229 子里 227 白）。"""
        assert plausible_position(board_with(black=2, white=227)) is False


class TestFrameGate:
    def test_first_frame_aligns_whole_position(self):
        """支持中途启动：首帧把盘上已有的子整体同步。"""
        gate = FrameGate()
        diff = [(1, x, 0) for x in range(6)] + [(-1, x, 1) for x in range(6)]
        accepted, reason = gate.accept(diff, board_with(black=6, white=6))
        assert reason == ""
        assert len(accepted) == 12

    def test_first_frame_rejected_when_implausible(self):
        gate = FrameGate()
        diff = [(-1, x, 0) for x in range(19)]
        accepted, reason = gate.accept(diff, board_with(black=2, white=227))
        assert accepted == []
        assert "失衡" in reason

    def test_rejects_bulk_frame_after_alignment(self):
        """对齐之后，一帧冒出十几颗必然是识别故障，整帧丢弃。"""
        gate = FrameGate()
        gate.accept([], board_with())
        diff = [(-1, x, 3) for x in range(10)]
        accepted, reason = gate.accept(diff, board_with(white=10))
        assert accepted == []
        assert "单帧新增 10 子" in reason

    def test_single_stone_needs_two_consecutive_frames(self):
        gate = FrameGate()
        gate.accept([], board_with())
        state = board_with(black=1)
        assert gate.accept([(1, 3, 3)], state) == ([], "")
        assert gate.accept([(1, 3, 3)], state) == ([(1, 3, 3)], "")

    def test_flicker_never_confirmed(self):
        """一闪就没的噪声（悬浮窗重绘、动画）永远攒不够帧数。"""
        gate = FrameGate()
        gate.accept([], board_with())
        for _ in range(5):
            assert gate.accept([(1, 3, 3)], board_with(black=1))[0] == []
            assert gate.accept([], board_with())[0] == []

    def test_two_stones_per_frame_allowed(self):
        """我方一手 + 对方一手可能同帧出现。"""
        gate = FrameGate()
        gate.accept([], board_with())
        diff = [(1, 3, 3), (-1, 15, 15)]
        state = board_with(black=1, white=1)
        gate.accept(diff, state)
        assert sorted(gate.accept(diff, state)[0]) == sorted(diff)

    def test_reset_restores_alignment(self):
        """stop() 后重开一局，应重新走首帧对齐而不是继续增量。"""
        gate = FrameGate()
        gate.accept([], board_with())
        gate.reset()
        diff = [(1, x, 0) for x in range(5)]
        assert gate.accept(diff, board_with(black=5))[0] == diff


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
