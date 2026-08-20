"""手动模式单元测试：假引擎 + 假悬浮窗验证轮次/同步/分析回调。"""
import os
import sys
import threading
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster.board_recognition import BoardModel, render_synthetic_board  # noqa: E402
from gomaster.config import Config  # noqa: E402
from gomaster.manual_mode import ManualMode  # noqa: E402


class FakeEngine:
    def __init__(self):
        self.played = []
        self.lock = threading.Lock()

    def start(self, board_size=19):
        pass

    def command(self, cmd):
        return "="

    def play(self, color, gtp):
        with self.lock:
            self.played.append((color, gtp))

    def analyze(self, color, seconds):
        return ([{"move": "Q4", "winrate": 0.62, "scoreLead": 1.5, "pv": ["Q4"]}],
                {"best": "Q4", "winrate": 0.62, "scoreLead": 1.5})

    def close(self):
        pass


class FakeOverlay:
    window_number = None

    def __init__(self, *a, **kw):
        self.updates = []

    def update(self, cands, recommend):
        self.updates.append((cands, recommend))

    def close(self):
        pass


def make_board():
    img = render_synthetic_board(19, [])
    h, w = img.shape[:2]
    m = 25
    return BoardModel(19, [(m, m), (w - m, m), (w - m, h - m), (m, h - m)])


def screenshot_fn(stones):
    def _fn():
        img = render_synthetic_board(19, stones)
        return img
    return _fn


class TestManualMode:
    def test_turn_color(self):
        mm = ManualMode(Config(), on_status=lambda s: None)
        mm.state = np.zeros((19, 19), dtype=int)
        assert mm._turn_color() == 1  # 空盘黑先
        mm.state[5, 5] = 1  # 黑一子
        assert mm._turn_color() == -1  # 轮白
        mm.state[6, 6] = -1
        assert mm._turn_color() == 1

    def test_sync_and_analyze(self):
        """对手落子 → 同步引擎 → 分析 → 悬浮窗更新。"""
        logs = []
        analyses = []
        mm = ManualMode(
            Config(interval=0.1, think_seconds=0.1),
            on_status=logs.append,
            on_analysis=lambda c, s: analyses.append((c, s)),
            overlay_factory=lambda *a, **kw: overlay,
        )
        mm.engine = FakeEngine()
        mm.board = make_board()
        overlay = FakeOverlay()
        engine = mm.engine  # stop() 后会置 None，先保存
        # 对手黑子落 (3,3)（图像坐标顶部）
        mm.screenshot_fn = screenshot_fn([(1, 3, 3)])
        mm.start()
        try:
            deadline = time.time() + 8
            while time.time() < deadline:
                if len(overlay.updates) > 0:
                    break
                time.sleep(0.2)
        finally:
            mm.stop()
        assert len(overlay.updates) > 0, "悬浮窗应收到分析更新"
        assert ("B", "D16") in engine.played  # (3,3) → GTP D16
        # 分析回调收到候选
        assert any(c[0][0]["move"] == "Q4" for c in analyses)
        # 对局记录
        assert len(mm.game_moves) >= 1

    def test_detect_new_stones(self):
        mm = ManualMode(Config())
        prev = np.zeros((19, 19), dtype=int)
        cur = np.zeros((19, 19), dtype=int)
        cur[4, 4] = 1
        cur[3, 3] = -1
        diff = mm._detect_new_stones(prev, cur)
        assert sorted(diff) == [(-1, 3, 3), (1, 4, 4)]

    def test_opponent_then_player_moves(self):
        """对手落子 → 玩家落子 → 双方都记录进 game_moves。"""
        logs = []
        mm = ManualMode(Config(interval=0.1, think_seconds=0.1),
                        on_status=logs.append,
                        overlay_factory=lambda *a, **kw: FakeOverlay())
        mm.engine = FakeEngine()
        mm.board = make_board()
        engine = mm.engine
        # 局面随调用次数演化：先对手黑 (3,3)，再玩家白 (15,15)
        stones_seq = [[(1, 3, 3)], [(1, 3, 3), (-1, 15, 15)]]
        seq_idx = [0]

        def shot():
            i = min(seq_idx[0], len(stones_seq) - 1)
            seq_idx[0] += 1
            return render_synthetic_board(19, stones_seq[i])

        mm.screenshot_fn = shot
        mm.start()
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                if len(mm.game_moves) >= 2:
                    break
                time.sleep(0.2)
        finally:
            mm.stop()
        assert len(mm.game_moves) >= 2
        # 第一手对手黑 (3,3) → D16，第二手白 (15,15) → Q4
        assert mm.game_moves[0][0] == 1 and mm.game_moves[0][3] == "D16"
        assert any(m[0] == -1 for m in mm.game_moves)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
