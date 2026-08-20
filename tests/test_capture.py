"""屏幕捕捉单元测试：显示器枚举与几何（用假 mss，不碰真实屏幕）。"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gomaster import capture  # noqa: E402
from gomaster.capture import PRIMARY, Monitor  # noqa: E402

# 实测的双屏布局：内置屏在原点，外接屏在负坐标
FAKE_MONITORS = [
    {"left": -1920, "top": -59, "width": 3432, "height": 1080},  # [0] 拼接虚拟屏
    {"left": 0, "top": 0, "width": 1512, "height": 982},         # [1] 内置屏
    {"left": -1920, "top": -59, "width": 1920, "height": 1080},  # [2] 外接屏
]


class FakeShot:
    def __init__(self, w, h):
        self.width, self.height = w, h
        self.__array_interface__ = np.zeros((h, w, 4), dtype=np.uint8).__array_interface__


class FakeMSS:
    """按 scale 放大截图尺寸，模拟高 DPI 下截图为物理像素的情况。"""

    scale = 1.0

    def __init__(self):
        self.monitors = FAKE_MONITORS
        self.grabbed = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def grab(self, mon):
        self.grabbed = mon
        return FakeShot(int(mon["width"] * self.scale), int(mon["height"] * self.scale))


@pytest.fixture
def fake_mss(monkeypatch):
    monkeypatch.setattr(capture, "_HAS_MSS", True)
    monkeypatch.setattr(capture, "_MSS", FakeMSS)
    FakeMSS.scale = 1.0
    return FakeMSS


class TestMonitor:
    def test_origin(self):
        assert Monitor(2, -1920, -59, 1920, 1080).origin == (-1920, -59)

    def test_label_contains_geometry(self):
        assert "1920×1080" in Monitor(2, -1920, -59, 1920, 1080).label()


class TestListMonitors:
    def test_skips_virtual_composite(self, fake_mss):
        mons = capture.list_monitors()
        assert [m.index for m in mons] == [1, 2]

    def test_keeps_negative_origin(self, fake_mss):
        """副屏原点为负是真实布局，不能被归零，否则点击整体偏移。"""
        assert capture.list_monitors()[1].origin == (-1920, -59)

    def test_empty_without_mss(self, monkeypatch):
        monkeypatch.setattr(capture, "_HAS_MSS", False)
        assert capture.list_monitors() == []


class TestGrabScreen:
    def test_grabs_requested_monitor(self, fake_mss):
        img = capture.grab_screen(2)
        assert img.shape == (1080, 1920, 3)  # BGRA → BGR

    def test_defaults_to_primary(self, fake_mss):
        assert capture.grab_screen().shape == (982, 1512, 3)

    def test_out_of_range_falls_back_to_primary(self, fake_mss):
        """配置里存了已拔掉的屏序号时不应崩溃。"""
        assert capture.grab_screen(9).shape == (982, 1512, 3)

    def test_none_without_mss(self, monkeypatch):
        monkeypatch.setattr(capture, "_HAS_MSS", False)
        assert capture.grab_screen() is None


class TestMeasureScale:
    def test_unity_when_screenshot_matches_points(self, fake_mss):
        assert capture.measure_scale(PRIMARY) == 1.0

    def test_detects_retina_doubling(self, fake_mss):
        fake_mss.scale = 2.0
        assert capture.measure_scale(PRIMARY) == 2.0

    def test_unity_without_mss(self, monkeypatch):
        monkeypatch.setattr(capture, "_HAS_MSS", False)
        assert capture.measure_scale() == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
