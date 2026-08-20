"""
手动模式：识别屏幕棋盘 → KataGo 持续分析当前局面 → 悬浮窗显示
推荐落点 + 各候选点实时胜率；玩家自己点击落子，识别确认后继续分析。

与全自动模式（main_loop）共享识别/引擎，但不自动点击。
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

import numpy as np

from .board_recognition import BoardModel, find_board_auto, recognize_stones
from .autoplayer import cursor_board_point
from .capture import grab_screen, resolve_geometry
from .config import Config
from .katago_client import KataGoClient
from .overlay import BoardOverlay


class ManualMode:
    def __init__(self, config: Config,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_analysis: Optional[Callable[[List[dict], dict], None]] = None,
                 on_state: Optional[Callable[[np.ndarray], None]] = None,
                 screenshot_fn: Optional[Callable[[], np.ndarray]] = None,
                 overlay_factory=None):
        """
        on_analysis(cands, summary): 每次分析完成回调（更新面板）
        overlay_factory(board, x, y, w, h): 创建悬浮窗（测试可注入假窗）
        """
        self.config = config
        self.on_status = on_status or (lambda s: None)
        self.on_analysis = on_analysis or (lambda c, s: None)
        self.on_state = on_state or (lambda s: None)
        self.screenshot_fn = screenshot_fn
        self.board: Optional[BoardModel] = None
        self.state = np.zeros((config.board_size, config.board_size), dtype=int)
        self.engine: Optional[KataGoClient] = None
        self.overlay: Optional[BoardOverlay] = None
        self._overlay_factory = overlay_factory
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # 对局记录（供复盘）：[(player, x, y, gtp)]
        self.game_moves: List[Tuple[int, int, int, str]] = []
        self.last_summary: Optional[dict] = None
        self.my_color: Optional[str] = None
        # 识别抖动保护：同一位置只记录一次
        self._last_synced: set = set()
        self._origin, self._scale = (0, 0), 1.0

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.overlay:
            self.overlay.close()
            self.overlay = None
        if self.engine:
            self.engine.close()
            self.engine = None

    def _grab(self) -> Optional[np.ndarray]:
        if self.screenshot_fn is not None:
            return self.screenshot_fn()
        # 排除自家悬浮窗，否则它画的候选点圆圈会被当成棋子
        below = self.overlay.window_number if self.overlay else None
        return grab_screen(self.config.monitor, below_window=below)

    def set_board(self, board: BoardModel, state: Optional[np.ndarray] = None) -> None:
        self.board = board
        if state is not None:
            self.state = state

    # ------------------------------------------------------------------
    def _run(self) -> None:
        self.on_status("启动引擎...")
        try:
            if self.engine is None:  # 测试可注入假引擎
                self.engine = KataGoClient(
                    self.config.katago_path, self.config.model_path, self.config.config_path,
                    num_search_threads=self.config.num_search_threads)
                self.engine.start(self.config.board_size)
                self.engine.command("komi 7.5")
        except Exception as e:
            self.on_status(f"引擎启动失败: {e}")
            return

        self._origin, self._scale = resolve_geometry(self.config.monitor)

        # 校准
        self.on_status("等待棋盘校准（自动检测或手动拖角）...")
        calib_wait = time.time() + 30
        while not self._stop.is_set():
            if self.board is not None:
                break
            img = self._grab()
            if img is not None:
                b = find_board_auto(img, size=self.config.board_size)
                if b is not None:
                    self.board = b
                    self.on_status("自动检测到棋盘 ✓")
                    break
            if time.time() > calib_wait:
                self.on_status("未检测到棋盘：请在界面手动校准四个角")
                break
            time.sleep(1.0)

        # 创建悬浮窗（叠加在棋盘外框位置）
        if self.board is not None and len(self.board.corners) == 4:
            self._create_overlay()

        self.on_status("手动模式运行中（悬浮窗显示 AI 建议，点击棋盘落子）...")
        last_state = np.zeros_like(self.state)
        last_analysis = 0.0
        while not self._stop.is_set():
            try:
                if self.board is None:
                    time.sleep(0.5)
                    continue
                img = self._grab()
                if img is None:
                    time.sleep(0.3)
                    continue
                state = recognize_stones(img, self.board)
                self._mask_cursor(state, last_state)
                self.state = state
                self.on_state(state)

                diff = self._detect_new_stones(last_state, state)
                if diff:
                    # 新棋子 → 同步引擎 + 记录对局（去重）
                    for color, x, y in diff:
                        gtp = self.board.to_gtp(x, y)
                        key = (color, x, y)
                        if key not in self._last_synced:
                            self._last_synced.add(key)
                            try:
                                self.engine.play("B" if color == 1 else "W", gtp)
                            except Exception as e:
                                self.on_status(f"引擎同步失败: {e}")
                            self.game_moves.append((color, x, y, gtp))
                            self.on_status(f"落子 {gtp}")
                    last_state = state.copy()

                # 持续分析（节流：至少间隔 1.5 秒，避免刷屏/引擎过载）
                now = time.time()
                if now - last_analysis >= 1.5:
                    last_analysis = now
                    self._analyze()

                time.sleep(max(0.2, self.config.interval))
            except Exception as e:
                self.on_status(f"循环异常: {e}")
                time.sleep(1.0)

    # ------------------------------------------------------------------
    def _analyze(self) -> None:
        if not self.engine:
            return
        color = "B" if self._turn_color() == 1 else "W"
        try:
            cands, summary = self.engine.analyze(color, self.config.think_seconds)
            self.last_summary = summary
            # 推荐点（GTP → (x, y)）
            recommend = self.board.from_gtp(summary["best"]) if self.board else None
            if self.overlay:
                self.overlay.update(cands, recommend)
            self.on_analysis(cands, summary)
            self.on_status(f"分析: 推荐 {summary['best']}（胜率 {summary['winrate']:.0%}）")
        except Exception as e:
            self.on_status(f"分析失败: {e}")

    def _turn_color(self) -> int:
        """当前该谁走：黑先对局，黑白子数相等 → 黑走。"""
        black = int(np.count_nonzero(self.state == 1))
        white = int(np.count_nonzero(self.state == -1))
        return 1 if black <= white else -1

    def _create_overlay(self) -> None:
        try:
            corners = self.board.corners
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            x0, y0 = int(min(xs)), int(min(ys))
            x1, y1 = int(max(xs)), int(max(ys))
            w, h = max(100, x1 - x0), max(100, y1 - y0)
            if self._overlay_factory:
                self.overlay = self._overlay_factory(self.board, x0, y0, w, h)
            elif threading.current_thread() is threading.main_thread():
                self.overlay = BoardOverlay(self.board, x0, y0, w, h,
                                            show_coords=self.config.overlay_coords)
            else:
                self.on_status("悬浮窗只能在主线程创建，已跳过（请从图形界面启动）")
        except Exception as e:
            self.on_status(f"悬浮窗创建失败: {e}")

    def _mask_cursor(self, state: np.ndarray, confirmed: np.ndarray) -> None:
        """抹掉光标压住那一点：平台在光标下画的"待落子"指示块会被识别成真子。

        玩家自己落子后光标仍停在该点，这一手要等光标移开才会被记录 —— 可自愈，
        而误把指示块当成落子会把假棋同步进引擎，不可逆。
        """
        pt = cursor_board_point(self.board, self._origin, self._scale)
        if pt is None:
            return
        x, y = pt
        state[y, x] = confirmed[y, x]

    @staticmethod
    def _detect_new_stones(prev: np.ndarray, cur: np.ndarray) -> List[Tuple[int, int, int]]:
        out = []
        for y in range(cur.shape[0]):
            for x in range(cur.shape[1]):
                if cur[y, x] != 0 and prev[y, x] == 0:
                    out.append((int(cur[y, x]), x, y))
        return out
