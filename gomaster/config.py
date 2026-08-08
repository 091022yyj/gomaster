"""配置管理：引擎路径 / 思考时间 / 执棋颜色 / 轮询间隔 等。"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, fields
from typing import Optional


def default_config_path() -> str:
    """配置文件默认位置：打包后为 exe 同目录，源码运行时为项目目录。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "gomaster_config.json")
    return "gomaster_config.json"


@dataclass
class Config:
    katago_path: str = ""
    model_path: str = ""
    config_path: str = ""
    board_size: int = 19
    num_search_threads: int = 64    # 引擎搜索线程数（256 在部分显卡上会阻塞分析，默认 64）
    think_seconds: float = 5.0      # 每手思考时间
    my_color: str = "auto"          # "B" 执黑 / "W" 执白 / "auto" 自动判断
    interval: float = 1.0           # 轮询间隔（秒）
    click_delay: float = 0.4        # 落子点击后的等待（秒）
    auto_click: bool = True         # 是否自动模拟点击（False = 仅分析提示）
    verify_moves: bool = True       # 落子后验证平台是否接受
    overlay_coords: bool = True     # 悬浮窗显示坐标标号
    sound: bool = True              # 落子提示音

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        if path is None:
            path = default_config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid = {f.name: f.default for f in fields(cls)}
                valid.update({k: v for k, v in data.items() if k in valid})
                return cls(**valid)
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self, path: Optional[str] = None) -> None:
        if path is None:
            path = default_config_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
