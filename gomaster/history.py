"""
对局记录：自动保存（JSON）、战绩统计、SGF 导出。
保存位置：项目目录（源码运行）或用户数据目录（打包运行）下 go_master_data/games.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional

from .config import frozen_base_dir


def data_dir() -> str:
    if getattr(sys, "frozen", False):
        base = frozen_base_dir()
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(base, "go_master_data")
    os.makedirs(d, exist_ok=True)
    return d


def games_path() -> str:
    return os.path.join(data_dir(), "games.json")


def _load_games() -> List[dict]:
    try:
        with open(games_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_game(moves: List[tuple], komi: float = 7.5, source: str = "manual",
              result: Optional[str] = None) -> dict:
    """保存一局。moves: [(player, x, y)]（player 1 黑 -1 白，x/y 交叉点）。"""
    games = _load_games()
    rec = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "komi": komi,
        "moves": [[m[0], m[1], m[2]] for m in moves],
        "result": result or "",
    }
    games.append(rec)
    games = games[-30:]  # 保留最近 30 局
    try:
        with open(games_path(), "w", encoding="utf-8") as f:
            json.dump(games, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return rec


def list_games() -> List[dict]:
    return _load_games()


def stats() -> dict:
    """战绩统计：总局数/胜/负。result: 'B' 黑胜 / 'W' 白胜 / 'D' 和。"""
    games = _load_games()
    total = len(games)
    wins = sum(1 for g in games if g.get("result") in ("B", "W"))
    losses = sum(1 for g in games if g.get("result") not in ("B", "W", "D", ""))
    draws = sum(1 for g in games if g.get("result") == "D")
    return {"total": total, "wins": wins, "losses": losses, "draws": draws,
            "win_rate": wins / total if total else 0.0}


def moves_to_sgf(moves: List[tuple], size: int = 19, komi: float = 7.5) -> str:
    """moves: [(player, x, y)] → SGF 字符串。"""
    cols = "abcdefghijklmnopqrstuvwxyz"
    parts = [f"(;GM[1]FF[4]SZ[{size}]KM[{komi}]"]
    for player, x, y in moves:
        color = "B" if player == 1 else "W"
        if 0 <= x < size and 0 <= y < size:
            parts.append(f"{color}[{cols[x]}{cols[y]}]")
        else:
            parts.append(f"{color}[]")
    parts.append(")")
    return "".join(parts)


def export_sgf(moves: List[tuple], path: Optional[str] = None,
               size: int = 19, komi: float = 7.5) -> Optional[str]:
    """导出 SGF 文件，返回路径。"""
    if not moves:
        return None
    if path is None:
        path = os.path.join(data_dir(), f"game_{int(time.time())}.sgf")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(moves_to_sgf(moves, size, komi))
        return path
    except OSError:
        return None
