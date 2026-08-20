"""屏幕捕捉：单块显示器截图（mss，跨平台）。

抓单块屏而非拼接虚拟屏：多显示器下各屏原点不同（macOS 副屏常在负坐标），
只有锁定一块屏，"图像坐标 → 屏幕坐标" 才有唯一解，自动落子才不会偏。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

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


def grab_screen(index: int = PRIMARY) -> Optional[np.ndarray]:
    """截取第 index 块物理屏，返回 BGR 图像（OpenCV 格式）；失败返回 None。"""
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
