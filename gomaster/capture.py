"""屏幕捕捉：单块显示器截图（mss，跨平台）。

抓单块屏而非拼接虚拟屏：多显示器下各屏原点不同（macOS 副屏常在负坐标），
只有锁定一块屏，"图像坐标 → 屏幕坐标" 才有唯一解，自动落子才不会偏。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

try:
    import mss
    _MSS = getattr(mss, "MSS", None) or mss.mss
    _HAS_MSS = True
except Exception:  # 无显示器/未安装 → 截图不可用（返回 None）
    _HAS_MSS = False

PRIMARY = 1  # mss 约定：monitors[0] 是拼接虚拟屏，物理屏从 1 开始


@dataclass(frozen=True)
class Monitor:
    """一块物理显示器的几何信息（逻辑点坐标系，与鼠标坐标同量纲）。"""

    index: int
    left: int
    top: int
    width: int
    height: int

    @property
    def origin(self) -> Tuple[int, int]:
        return self.left, self.top

    def label(self) -> str:
        return f"屏幕 {self.index}（{self.width}×{self.height} @ {self.left},{self.top}）"


def list_monitors() -> List[Monitor]:
    """枚举物理显示器；截图不可用时返回空列表。"""
    if not _HAS_MSS:
        return []
    try:
        with _MSS() as sct:
            return [Monitor(i, m["left"], m["top"], m["width"], m["height"])
                    for i, m in enumerate(sct.monitors) if i >= PRIMARY]
    except Exception:
        return []


def _cgimage_to_bgr(image) -> np.ndarray:
    import Quartz as Q

    width, height = Q.CGImageGetWidth(image), Q.CGImageGetHeight(image)
    stride = Q.CGImageGetBytesPerRow(image)
    data = Q.CGDataProviderCopyData(Q.CGImageGetDataProvider(image))
    buf = np.frombuffer(data, dtype=np.uint8)[:stride * height]
    return buf.reshape(height, stride // 4, 4)[:, :width, :3].copy()  # BGRA → BGR


def _grab_below_window(mon: Monitor, window_number: int) -> Optional[np.ndarray]:
    """只截取指定窗口以下的画面（macOS）。

    悬浮窗就画在棋盘上方，整屏截图会把它自己拍进去，候选点圆圈随即被
    recognize_stones 当成棋子、当成对手落子同步进引擎，形成
    "画标记 → 认成子 → 分析变化 → 画新标记" 的反馈回路。
    """
    try:
        import Quartz as Q

        image = Q.CGWindowListCreateImage(
            Q.CGRectMake(mon.left, mon.top, mon.width, mon.height),
            Q.kCGWindowListOptionOnScreenBelowWindow, window_number,
            Q.kCGWindowImageNominalResolution)
        if image is None:
            return None
        bgr = _cgimage_to_bgr(image)
    except Exception:
        return None
    # 统一成逻辑点尺寸：与 mss 口径一致，坐标换算才不用分叉
    if (bgr.shape[1], bgr.shape[0]) != (mon.width, mon.height):
        bgr = cv2.resize(bgr, (mon.width, mon.height), interpolation=cv2.INTER_AREA)
    return bgr


def grab_screen(index: int = PRIMARY,
                below_window: Optional[int] = None) -> Optional[np.ndarray]:
    """截取第 index 块物理屏，返回 BGR 图像（OpenCV 格式）；失败返回 None。

    below_window 给定时只截该窗口以下的内容，用于把自家悬浮窗排除在识别之外。
    """
    if below_window is not None and sys.platform == "darwin":
        for mon in list_monitors():
            if mon.index == index:
                shot = _grab_below_window(mon, below_window)
                if shot is not None:
                    return shot
                break  # Quartz 不可用则退回 mss（会拍到悬浮窗，但好过没有画面）
    if not _HAS_MSS:
        return None
    try:
        with _MSS() as sct:
            mon = sct.monitors[index if index < len(sct.monitors) else PRIMARY]
            shot = sct.grab(mon)
            # mss 返回 BGRA → 转 BGR
            return np.array(shot)[:, :, :3].copy()
    except Exception:
        return None


def resolve_geometry(index: int = PRIMARY) -> Tuple[Tuple[int, int], float]:
    """返回该屏的 (原点, 缩放)，供图像坐标 ↔ 屏幕坐标互转；找不到时回落到原点无缩放。"""
    for mon in list_monitors():
        if mon.index == index:
            return mon.origin, measure_scale(index)
    return (0, 0), 1.0


def measure_scale(index: int = PRIMARY) -> float:
    """截图像素 / 逻辑点 的比值。

    macOS + mss 10 下为 1.0（mss 已归一到逻辑点）；Windows 高 DPI 下可能为 2.0。
    映射屏幕坐标时必须除掉它，否则整盘偏移。
    """
    if not _HAS_MSS:
        return 1.0
    try:
        with _MSS() as sct:
            mon = sct.monitors[index if index < len(sct.monitors) else PRIMARY]
            if not mon["width"]:
                return 1.0
            return sct.grab(mon).width / float(mon["width"])
    except Exception:
        return 1.0
