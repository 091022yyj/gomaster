"""围棋规则单元测试：提子/劫/禁着/停一手/终局数子/SGF。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.go_rules import (  # noqa: E402
    create_board,
    count_score,
    is_legal_move,
    pass_turn,
    place_stone,
    sgf_to_state,
    state_to_sgf,
    undo,
    winner,
)


def _p(x, y):
    return (x, y)


class TestBasic:
    def test_alternate_turns(self):
        s = create_board()
        s = place_stone(s, _p(3, 3))
        assert s.turn == -1
        s = place_stone(s, _p(15, 15))
        assert s.turn == 1
        assert s.stones[s.size * 3 + 3] == 1
        assert s.stones[s.size * 15 + 15] == -1

    def test_occupied_rejected(self):
        s = create_board()
        s = place_stone(s, _p(3, 3))
        with pytest.raises(ValueError):
            place_stone(s, _p(3, 3))

    def test_suicide_rejected(self):
        """落子后无气且不提对方子 = 自杀，应被拒绝。"""
        s = create_board()
        s = place_stone(s, _p(9, 9))   # 黑闲
        s = place_stone(s, _p(1, 0))   # 白
        s = place_stone(s, _p(8, 8))   # 黑闲
        s = place_stone(s, _p(0, 1))   # 白
        # 黑 (0,0)：邻居全白且白都有气 → 自杀
        with pytest.raises(ValueError):
            place_stone(s, _p(0, 0))
        # 但落子能提子时允许（提子优先）
        s2 = create_board()
        # 白 (1,0) 单子被黑 (0,1)(1,1)? 构造黑提白：
        s2 = place_stone(s2, _p(1, 1))  # 黑
        s2 = place_stone(s2, _p(1, 0))  # 白
        s2 = place_stone(s2, _p(0, 1))  # 黑 围 (1,0) 剩 (0,0)? 不对，(1,0) 气=(0,0)(2,0)(1,1黑)(0,1黑)
        # 简化：黑 (0,1)(2,1)(1,2) 围白 (1,1)? 白 (1,1) 气=(1,0)(1,2黑)(0,1黑)(2,1黑)
        s3 = create_board()
        s3 = place_stone(s3, _p(1, 2))  # 黑
        s3 = place_stone(s3, _p(1, 1))  # 白
        s3 = place_stone(s3, _p(0, 1))  # 黑
        s3 = place_stone(s3, _p(9, 9))  # 白闲
        s3 = place_stone(s3, _p(2, 1))  # 黑 围白 (1,1) 剩 (1,0)
        s3 = place_stone(s3, _p(8, 8))  # 白闲
        # 黑 (1,0) 落子：提白 (1,1)（无气）→ 合法
        s3 = place_stone(s3, _p(1, 0))
        assert s3.stones[s3.size * 1 + 1] == 0  # 白被提


class TestCapture:
    def test_capture_single_stone(self):
        s = create_board()
        # 黑 (1,0) 孤子；白围 (0,1)(1,1)(2,0)，黑闲棋周转，白 (0,0) 提
        s = place_stone(s, _p(1, 0))   # 黑
        s = place_stone(s, _p(0, 1))   # 白
        s = place_stone(s, _p(9, 9))   # 黑闲
        s = place_stone(s, _p(1, 1))   # 白
        s = place_stone(s, _p(8, 8))   # 黑闲
        s = place_stone(s, _p(2, 0))   # 白
        s = place_stone(s, _p(7, 7))   # 黑闲
        s = place_stone(s, _p(0, 0))   # 白提 (1,0)
        assert s.stones[s.size * 0 + 1] == 0
        assert s.captured["white"] == 1  # 白提了 1 子

    def test_capture_group(self):
        """整组无气被提。"""
        s = create_board()
        # 黑 (0,0)(1,0)(0,1) 角部三角，白围外侧后提整组
        s = place_stone(s, _p(0, 0))   # 黑
        s = place_stone(s, _p(2, 0))   # 白
        s = place_stone(s, _p(1, 0))   # 黑
        s = place_stone(s, _p(3, 0))   # 白
        s = place_stone(s, _p(0, 1))   # 黑
        s = place_stone(s, _p(0, 2))   # 白
        s = place_stone(s, _p(9, 9))   # 黑闲
        s = place_stone(s, _p(1, 1))   # 白
        s = place_stone(s, _p(8, 8))   # 黑闲
        s = place_stone(s, _p(1, 2))   # 白
        s = place_stone(s, _p(7, 7))   # 黑闲
        s = place_stone(s, _p(2, 1))   # 白 提黑三角
        assert s.stones[s.size * 0 + 0] == 0
        assert s.stones[s.size * 0 + 1] == 0
        assert s.stones[s.size * 1 + 0] == 0
        assert s.captured["white"] == 3

    def test_ko_forbidden(self):
        """打劫：提一子成劫后，立即回提被禁止。"""
        s = create_board()
        # 与 go-battle board.test.ts 相同构造：
        # 黑(1,0) 被白(0,0)(2,0)(0,1)(1,1) 围提，白(1,1) 提黑(1,0) 成劫
        s = place_stone(s, _p(1, 0))   # 黑
        s = place_stone(s, _p(0, 0))   # 白
        s = place_stone(s, _p(8, 8))   # 黑闲
        s = place_stone(s, _p(2, 0))   # 白
        s = place_stone(s, _p(7, 7))   # 黑闲
        s = place_stone(s, _p(0, 1))   # 白
        s = place_stone(s, _p(6, 6))   # 黑闲
        s = place_stone(s, _p(1, 1))   # 白提黑(1,0)，形成劫
        assert s.stones[s.size * 0 + 1] == 0  # (1,0) 被提
        assert s.captured["white"] == 1
        assert s.ko == (1, 0)  # 劫点 = 被提的黑子位置
        assert is_legal_move(s, _p(1, 0)) is False  # 黑不能立即回提
        # 黑走别处 → 劫解除
        s2 = place_stone(s, _p(5, 5))
        assert s2.ko is None
        assert is_legal_move(s2, _p(1, 0)) is True  # 白可以下 (1,0)（非提劫）

    def test_pass_ends_game(self):
        s = create_board()
        s = place_stone(s, _p(3, 3))
        s = pass_turn(s)
        assert s.finished is False
        s = pass_turn(s)
        assert s.finished is True


class TestScore:
    def test_empty_board(self):
        s = create_board(9)
        r = count_score(s, "area", 7.5)
        assert r["black"] == 0 and r["white"] == 0
        # 空盘无子：黑-白=0 不超贴目 → 平局（0）
        assert winner(s, "area", 7.5) == 0
    def test_full_board_area(self):
        """全黑盘：黑 81 目，黑胜。"""
        s = create_board(9)
        # 全黑（非轮转摆法：直接构造）
        s.stones = [1] * 81
        r = count_score(s, "area", 7.5)
        assert r["black"] == 81
        assert winner(s, "area", 7.5) == 1

    def test_sgf_roundtrip(self):
        s = create_board()
        s = place_stone(s, _p(3, 3))
        s = place_stone(s, _p(15, 15))
        s = pass_turn(s)
        sgf = state_to_sgf(s)
        s2 = sgf_to_state(sgf)
        assert s2.stones == s.stones
        assert s2.turn == s.turn
        assert len(s2.history) == 3

    def test_undo(self):
        s = create_board()
        s = place_stone(s, _p(3, 3))
        s = place_stone(s, _p(15, 15))
        s2 = undo(s)
        assert len(s2.history) == 1
        assert s2.stones[s2.size * 15 + 15] == 0
        assert s2.turn == -1  # 轮到白（黑子仍在）


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
