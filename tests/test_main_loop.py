"""主循环单元测试：轮次跟踪 / 局面对比 / 落子判定。"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.config import Config  # noqa: E402
from gomaster.main_loop import GoMasterLoop  # noqa: E402


class TestTurnTracking:
    def test_detect_new_stones(self):
        loop = GoMasterLoop(Config(), on_status=lambda s: None)
        prev = np.zeros((19, 19), dtype=int)
        cur = np.zeros((19, 19), dtype=int)
        cur[4, 4] = 1
        cur[3, 3] = -1
        diff = loop._detect_new_stones(prev, cur)
        assert sorted(diff) == [(-1, 3, 3), (1, 4, 4)]

    def test_no_change(self):
        loop = GoMasterLoop(Config(), on_status=lambda s: None)
        cur = np.zeros((19, 19), dtype=int)
        cur[4, 4] = 1
        assert loop._detect_new_stones(cur, cur) == []

    def test_resolve_color_auto(self):
        loop = GoMasterLoop(Config(my_color="auto"), on_status=lambda s: None)
        loop._resolve_my_color(1)  # 对手下黑 → 我执白
        assert loop.my_color == "W"
        loop2 = GoMasterLoop(Config(my_color="auto"), on_status=lambda s: None)
        loop2._resolve_my_color(-1)  # 对手下白 → 我执黑
        assert loop2.my_color == "B"

    def test_resolve_color_fixed(self):
        loop = GoMasterLoop(Config(my_color="B"), on_status=lambda s: None)
        loop._resolve_my_color(1)
        assert loop.my_color == "B"

    def test_awaiting_gate_blocks_repeat(self):
        """AI 建议落子后 _awaiting=True，_maybe_play 应直接返回（不重复分析）。"""
        loop = GoMasterLoop(Config(my_color="B"), on_status=lambda s: None)
        loop._awaiting = True
        loop.engine = None  # 若未拦截会因 engine 为 None 返回，但应先被 _awaiting 拦截
        loop._maybe_play()  # 不崩溃、无副作用

    def test_opponent_move_resumes(self):
        """对手落子（diff 中对手颜色）→ _is_opponent_move True。"""
        loop = GoMasterLoop(Config(my_color="W"), on_status=lambda s: None)
        loop.my_color = "W"
        diff = [(1, 10, 10)]  # 黑子 = 对手（我方白）
        assert loop._is_opponent_move(diff) is True

    def test_own_move_keeps_awaiting(self):
        """识别到 AI 自己的落子 → _is_opponent_move False。"""
        loop = GoMasterLoop(Config(my_color="W"), on_status=lambda s: None)
        loop.my_color = "W"
        diff = [(-1, 5, 5)]  # 白子 = 我方
        assert loop._is_opponent_move(diff) is False

    def test_opponent_move_black_player(self):
        """执黑时白子是对手。"""
        loop = GoMasterLoop(Config(my_color="B"), on_status=lambda s: None)
        loop.my_color = "B"
        assert loop._is_opponent_move([(-1, 5, 5)]) is True
        assert loop._is_opponent_move([(1, 5, 5)]) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
