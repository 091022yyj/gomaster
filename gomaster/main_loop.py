"""
主循环：截图 → 识别棋盘 → 对比变化跟踪轮次 → 轮到 AI 时分析并落子。

轮次跟踪（turn tracking）设计：
- 不依赖 OCR：每帧识别局面，与上一帧对比发现"新出现的棋子"，
  该棋子颜色即对手刚下的手 → 轮次自然切换。
- 用户可选配置执黑/执白/自动：auto 时第一手识别到黑子落子则 AI 执白，反之执黑。
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

import numpy as np

from .board_recognition import BoardModel, FrameGate, recognize_stones, find_board_auto
from .capture import grab_screen, resolve_geometry
from .config import Config
from .katago_client import KataGoClient
from .autoplayer import AutoPlayer, cursor_board_point


class GoMasterLoop:
    def __init__(self, config: Config, on_status: Optional[Callable[[str], None]] = None,
                 on_state: Optional[Callable[[np.ndarray], None]] = None,
                 on_analysis: Optional[Callable[[List, dict], None]] = None,
                 screenshot_fn: Optional[Callable[[], np.ndarray]] = None):
        self.config = config
        self.on_status = on_status or (lambda s: None)
        self.on_state = on_state or (lambda s: None)
        self.on_analysis = on_analysis or (lambda c, s: None)
        self.screenshot_fn = screenshot_fn  # 注入截图（测试用合成图）；缺省抓配置指定的屏
        self.board: Optional[BoardModel] = None
        self.state = np.zeros((config.board_size, config.board_size), dtype=int)
        self.engine: Optional[KataGoClient] = None
        self.player = AutoPlayer(config.click_delay)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # 状态
        self.my_color: Optional[str] = None   # 解析后的 "B" / "W"
        self.last_ai_move: Optional[str] = None
        self.moves_synced = 0
        self._awaiting = False  # AI 已建议/落子，等待对手落子后才能再次分析
        self._last_click_point: Optional[Tuple[int, int]] = None  # AI 刚点下的点（不做光标屏蔽）
        self._gate = FrameGate()
        # 对局记录（供面板/复盘/保存）
        self.game_moves: List[Tuple[int, int, int, str]] = []
        self.move_no = 0
        self._game_over_reported = False

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
        if self.engine:
            self.engine.close()
            self.engine = None
        self._gate.reset()

    def _grab(self) -> Optional[np.ndarray]:
        if self.screenshot_fn is not None:
            return self.screenshot_fn()
        return grab_screen(self.config.monitor)

    def _configure_player(self) -> None:
        """把选中屏幕的原点与缩放交给点击器，图像坐标才能换算成全局屏幕坐标。"""
        self.player.origin, self.player.scale = resolve_geometry(self.config.monitor)

    def _mask_cursor(self, state: np.ndarray, confirmed: np.ndarray) -> None:
        """抹掉光标压住那一点的识别结果，沿用上一帧的确认值。

        平台在光标下画的"待落子"指示块颜色随执棋方变化，会被识别成真子，
        进而当作对手落子同步进引擎，引擎棋盘从此永久错位。
        例外：AI 刚点下的那点是真子，抹掉会导致我方这手同步不进引擎。
        """
        pt = cursor_board_point(self.board, self.player.origin, self.player.scale)
        if pt is None or pt == self._last_click_point:
            return
        x, y = pt
        state[y, x] = confirmed[y, x]

    def set_board(self, board: BoardModel, state: Optional[np.ndarray] = None) -> None:
        """手动校准棋盘（GUI 拖拽角点后调用）。"""
        self.board = board
        if state is not None:
            self.state = state

    # ------------------------------------------------------------------
    def _run(self) -> None:
        self.on_status("启动引擎...")
        try:
            self.engine = KataGoClient(
                self.config.katago_path, self.config.model_path, self.config.config_path,
                num_search_threads=self.config.num_search_threads)
            self.engine.start(self.config.board_size)
            self.engine.command(f"komi {7.5}")
        except Exception as e:
            self.on_status(f"引擎启动失败: {e}")
            return
        self._configure_player()

        # 首次校准：尝试自动检测（或等待手动校准）
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

        self.on_status("开始运行（轮询中）...")
        last_state = np.zeros_like(self.state)
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

                # 与上次对比：新出现的棋子 = 对手落子
                raw_diff = self._detect_new_stones(last_state, state)
                diff, reason = self._gate.accept(raw_diff, state)
                if reason:
                    self.on_status(f"识别异常：{reason}，已丢弃该帧")
                if diff:
                    # 解析我方颜色（首次）
                    if self.my_color is None:
                        self._resolve_my_color(diff[0][0])
                    else:
                        # auto 模式：空盘默认执黑先手，若对手先落子
                        # （我方从未落子且对手已有子）则纠正为执白
                        if self.config.my_color == "auto":
                            my_player = 1 if self.my_color == "B" else -1
                            opp_player = -my_player
                            if (np.count_nonzero(state == my_player) == 0
                                    and np.count_nonzero(state == opp_player) > 0):
                                self._resolve_my_color(diff[0][0])
                    # 我方颜色对应的棋子数值
                    my_player = 1 if self.my_color == "B" else -1
                    for color, x, y in diff:
                        gtp = self.board.to_gtp(x, y)
                        self.on_status(f"检测到落子: {gtp}")
                        self._sync_engine(color, gtp)
                        if color != my_player:  # 对手落子计数（AI 落子由 _maybe_play 记录）
                            self.move_no += 1
                            self.game_moves.append((color, x, y, gtp))
                    for color, x, y in diff:
                        last_state[y, x] = color  # 只推进已采信的点
                    # 仅对手落子解除等待并触发分析；AI 自己落下的子保持等待
                    if self._is_opponent_move(diff):
                        self._awaiting = False
                        self._maybe_play()
                else:
                    # 无变化：解析我方颜色（auto 模式）
                    if self.my_color is None:
                        if np.count_nonzero(state) == 0:
                            # 空盘开局：默认黑先（若实际执白，对手首手黑子出现时纠正）
                            self.my_color = self.config.my_color if self.config.my_color in ("B", "W") else "B"
                            self.on_status(f"我方执{'黑' if self.my_color == 'B' else '白'}（空盘开局）")
                        else:
                            first = self._first_stone(state)
                            if first:
                                self._resolve_my_color(first[0])
                    # 无变化且轮到 AI（初始化后直接开始）时也尝试
                    self._maybe_play()

                time.sleep(max(0.2, self.config.interval))
            except Exception as e:
                self.on_status(f"循环异常: {e}")
                time.sleep(1.0)

    # ------------------------------------------------------------------
    def _detect_new_stones(self, prev: np.ndarray, cur: np.ndarray
                           ) -> List[Tuple[int, int, int]]:
        """对比两帧，返回新出现的棋子 [(color, x, y)]（按行扫描）。"""
        out = []
        for y in range(cur.shape[0]):
            for x in range(cur.shape[1]):
                if cur[y, x] != 0 and prev[y, x] == 0:
                    out.append((int(cur[y, x]), x, y))
        return out

    @staticmethod
    def _first_stone(state: np.ndarray) -> Optional[Tuple[int, int, int]]:
        for y in range(state.shape[0]):
            for x in range(state.shape[1]):
                if state[y, x] != 0:
                    return (int(state[y, x]), x, y)
        return None

    def _is_opponent_move(self, diff: List[Tuple[int, int, int]]) -> bool:
        """diff 中是否包含对手颜色的落子（用于解除 AI 等待）。"""
        if not diff:
            return False
        if self.my_color is None:
            return True
        my_player = 1 if self.my_color == "B" else -1
        return any(color != my_player for color, _, _ in diff)

    def _resolve_my_color(self, opp_color: int) -> None:
        """根据对手先手颜色解析我方执棋。opp_color: 1 黑 / -1 白。"""
        if self.config.my_color in ("B", "W"):
            self.my_color = self.config.my_color
        else:  # auto：对手下黑 → 我执白
            self.my_color = "W" if opp_color == 1 else "B"
        self.on_status(f"我方执{'黑' if self.my_color == 'B' else '白'}")

    def _sync_engine(self, color: int, gtp: str) -> None:
        """把对手的落子同步给引擎。"""
        if not self.engine:
            return
        c = "B" if color == 1 else "W"
        try:
            self.engine.play(c, gtp)
            self.moves_synced += 1
        except Exception as e:
            self.on_status(f"引擎同步失败: {e}")

    def _maybe_play(self) -> None:
        """如果轮到 AI 落子则分析并点击。"""
        if self.my_color is None or not self.engine:
            return
        # AI 已建议/落子，等待对手落子解除（避免同一局面反复分析）
        if self._awaiting:
            return
        # 我方颜色对应引擎中的我方棋子颜色
        if self.my_color == "B":
            my_player, opp_player = 1, -1
        else:
            my_player, opp_player = -1, 1
        mine = int(np.count_nonzero(self.state == my_player))
        opp = int(np.count_nonzero(self.state == opp_player))
        # 轮次判定（黑先对局）：
        #   执黑（先手）：子数平（含 0:0 开局）时轮到我
        #   执白（后手）：我子数少于对方（对方刚下完）时轮到我
        if self.my_color == "B":
            my_turn = mine == opp
        else:
            my_turn = mine < opp
        if not my_turn:
            return

        # 轮到 AI：分析并落子
        self.on_status("AI 思考中...")
        try:
            color = "B" if my_player == 1 else "W"
            cands, summary = self.engine.analyze(color, self.config.think_seconds)
            best = summary["best"]
            self.move_no += 1
            self.on_analysis(cands, summary)
            self.on_status(f"AI 推荐: {best}（胜率 {summary['winrate']:.0%}）")
            if best in ("pass", "resign"):
                self.on_status(f"AI {best}（不落子）")
                self._awaiting = True
                self.last_ai_move = best
                if best == "resign" and not self._game_over_reported:
                    self._game_over_reported = True
                    self.on_status("AI 认输，对局结束")
                return
            pt = self.board.from_gtp(best) if self.board else None
            if pt is None:
                self.on_status(f"AI 落子坐标异常: {best}")
                self._awaiting = True
                self.last_ai_move = best
                return
            if self.config.auto_click and self.board:
                if self.player.available():
                    if self.player.click_point(self.board, *pt) is not None:
                        self._last_click_point = pt
                        self.on_status(f"已点击落子 {best}")
                    else:
                        self.on_status(f"点击失败（{self.player.last_error}），建议落子 {best}")
                else:
                    self.on_status(f"自动点击不可用（缺少 pyautogui），建议落子 {best}")
            else:
                self.on_status(f"（自动点击关闭）建议落子 {best}")
            # 本地同步（实际落子后下一帧会识别确认）
            gx, gy = pt
            self.state[gy, gx] = my_player
            self.game_moves.append((my_player, gx, gy, best))
            # 已响应：等待对手落子或识别到我方落子后再继续
            self._awaiting = True
            self.last_ai_move = best
        except Exception as e:
            self.on_status(f"AI 分析失败: {e}")
