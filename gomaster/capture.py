"""屏幕捕捉：全屏截图（mss，跨平台）。"""
from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import mss
    _HAS_MSS = True
except Exception:  # 无显示器/未安装 → 截图不可用（返回 None）
    _HAS_MSS = False


def grab_screen() -> Optional[np.ndarray]:
    """全屏截图，返回 BGR 图像（OpenCV 格式）；失败返回 None。"""
    if not _HAS_MSS:
        return None
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            # mss 返回 BGRA → 转 BGR
            img = np.array(shot)[:, :, :3].copy()
            return img
    except Exception:
        return None
