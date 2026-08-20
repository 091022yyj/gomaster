"""自动落子单元测试：图像坐标 → 屏幕坐标换算 + 落点校验（不驱动真实鼠标）。"""
import os
import sys
from collections import namedtuple

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster import autoplayer as ap  # noqa: E402
from gomaster.autoplayer import AutoPlayer, cursor_board_point  # noqa: E402
from gomaster.board_recognition import BoardModel  # noqa: E402

Point = namedtuple("Point", "x y")


class FakeMouse:
    """假鼠标：drift 模拟系统把光标落到别处（实测跨显示器移动会发生）。"""

    def __init__(self, drift=(0.0, 0.0)):
        self.drift = drift
        self.pos = Point(0.0, 0.0)
        self.clicks = 0

    def moveTo(self, x, y):
        self.pos = Point(x + self.drift[0], y + self.drift[1])

    def position(self):
        return self.pos

    def click(self):
        self.clicks += 1


@pytest.fixture
def board():
    # 19 路，交叉点间距 10px，左上角在图像 (100, 100)
    return BoardModel(19, [(100, 100), (280, 100), (280, 280), (100, 280)])


@pytest.fixture
def fake_mouse(monkeypatch):
    mouse = FakeMouse()
    monkeypatch.setattr(ap, "pyautogui", mouse)
    monkeypatch.setattr(ap, "_HAS_PYAUTOGUI", True)
    return mouse


class TestToScreen:
    def test_identity_on_primary(self):
        p = AutoPlayer(origin=(0, 0), scale=1.0)
        assert p.to_screen(300.0, 400.0) == (300.0, 400.0)

    def test_applies_negative_origin(self):
        """macOS 副屏常在负坐标：截图原点必须加回去，否则整盘偏移。"""
        p = AutoPlayer(origin=(-1920, -59), scale=1.0)
        assert p.to_screen(10.0, 20.0) == (-1910.0, -39.0)

    def test_applies_retina_scale(self):
        """截图为物理像素、鼠标用逻辑点时，必须除掉缩放。"""
        p = AutoPlayer(origin=(0, 0), scale=2.0)
        assert p.to_screen(600.0, 400.0) == (300.0, 200.0)

    def test_origin_and_scale_combined(self):
        p = AutoPlayer(origin=(-1920, -59), scale=2.0)
        assert p.to_screen(200.0, 100.0) == (-1820.0, -9.0)


class TestCursorBoardPoint:
    """平台在光标下画的"待落子"指示块会被当成真子，必须先定位到是哪个交叉点。"""

    def test_maps_cursor_to_intersection(self, board, fake_mouse):
        fake_mouse.pos = Point(100.0, 100.0)
        assert cursor_board_point(board) == (0, 0)

    def test_accounts_for_monitor_origin(self, board, fake_mouse):
        fake_mouse.pos = Point(-1820.0, 41.0)
        assert cursor_board_point(board, origin=(-1920, -59)) == (0, 0)

    def test_accounts_for_scale(self, board, fake_mouse):
        fake_mouse.pos = Point(90.0, 90.0)  # 图像坐标 180,180 → 交叉点 (8, 8)
        assert cursor_board_point(board, scale=2.0) == (8, 8)

    def test_none_when_cursor_off_board(self, board, fake_mouse):
        fake_mouse.pos = Point(1000.0, 1000.0)
        assert cursor_board_point(board) is None

    def test_none_without_board(self, fake_mouse):
        assert cursor_board_point(None) is None

    def test_none_when_board_uncalibrated(self, fake_mouse):
        assert cursor_board_point(BoardModel(19, [])) is None


class TestClickVerification:
    def test_clicks_when_cursor_lands(self, board, fake_mouse):
        p = AutoPlayer(click_delay=0.0, origin=(0, 0), scale=1.0)
        got = p.click_point(board, 0, 0)
        assert got == (100.0, 100.0)
        assert fake_mouse.clicks == 1
        assert p.last_error == ""

    def test_refuses_click_when_cursor_drifts(self, board, fake_mouse):
        """光标没落到目标点就点击 = 下错一手，必须拒绝。"""
        fake_mouse.drift = (40.0, 0.0)
        p = AutoPlayer(click_delay=0.0, origin=(0, 0), scale=1.0)
        assert p.click_point(board, 3, 3) is None
        assert fake_mouse.clicks == 0
        assert "光标无法到达" in p.last_error

    def test_tolerates_sub_pixel_drift(self, board, fake_mouse):
        fake_mouse.drift = (1.0, -1.0)
        p = AutoPlayer(click_delay=0.0, origin=(0, 0), scale=1.0)
        assert p.click_point(board, 5, 5) is not None
        assert fake_mouse.clicks == 1

    def test_click_maps_through_origin(self, board, fake_mouse):
        p = AutoPlayer(click_delay=0.0, origin=(-1920, -59), scale=1.0)
        got = p.click_point(board, 0, 0)
        assert got == (-1820.0, 41.0)
        assert fake_mouse.pos == (-1820.0, 41.0)

    def test_unavailable_without_pyautogui(self, board, monkeypatch):
        monkeypatch.setattr(ap, "_HAS_PYAUTOGUI", False)
        p = AutoPlayer(click_delay=0.0)
        assert p.click_point(board, 0, 0) is None
        assert p.last_error == "未安装 pyautogui"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
