"""
纯 Python 围棋规则（翻译自 go-battle 的 board.ts / rules.ts）：
落子合法性（气/自杀/劫）、提子、停一手、终局数子（数空/计目）、SGF 转换。

state 表示：stones 一维数组（1=黑 -1=白 0=空），turn 1 黑先。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

NEIGHBORS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
SGF_COLS = "abcdefghijklmnopqrstuvwxyz"


@dataclass
class Move:
    player: int
    point: Optional[Tuple[int, int]] = None  # None = pass


@dataclass
class GameState:
    size: int = 19
    stones: List[int] = field(default_factory=list)
    turn: int = 1
    ko: Optional[Tuple[int, int]] = None
    captured: dict = field(default_factory=lambda: {"black": 0, "white": 0})
    history: List[Move] = field(default_factory=list)
    pass_count: int = 0
    finished: bool = False

    def __post_init__(self) -> None:
        if not self.stones:
            self.stones = [0] * (self.size * self.size)


def create_board(size: int = 19) -> GameState:
    return GameState(size=size)


def index_of(state: GameState, p: Tuple[int, int]) -> int:
    return p[1] * state.size + p[0]


def in_bounds(state: GameState, p: Tuple[int, int]) -> bool:
    return 0 <= p[0] < state.size and 0 <= p[1] < state.size


def neighbors(state: GameState, p: Tuple[int, int]) -> List[Tuple[int, int]]:
    return [(p[0] + dx, p[1] + dy) for dx, dy in NEIGHBORS if in_bounds(state, (p[0] + dx, p[1] + dy))]


def opponent(player: int) -> int:
    return 1 if player == -1 else -1


def get_group(state: GameState, p: Tuple[int, int]) -> List[Tuple[int, int]]:
    """返回 p 所在同色连通块（p 处必须已有棋子）。"""
    color = state.stones[index_of(state, p)]
    if color == 0:
        return []
    seen = {index_of(state, p)}
    queue = [p]
    group: List[Tuple[int, int]] = []
    while queue:
        cur = queue.pop()
        group.append(cur)
        for q in neighbors(state, cur):
            i = index_of(state, q)
            if i not in seen and state.stones[i] == color:
                seen.add(i)
                queue.append(q)
    return group


def get_liberties(state: GameState, group: List[Tuple[int, int]]) -> set:
    libs = set()
    for p in group:
        for q in neighbors(state, p):
            if state.stones[index_of(state, q)] == 0:
                libs.add(index_of(state, q))
    return libs


def is_legal_move(state: GameState, point: Tuple[int, int]) -> bool:
    if state.finished or not in_bounds(state, point):
        return False
    i = index_of(state, point)
    if state.stones[i] != 0:
        return False
    if state.ko and state.ko == point:
        return False

    player = state.turn
    stones = list(state.stones)
    stones[i] = player

    # 能提对方子 → 合法（含提后自己有气的情况）
    for q in neighbors(state, point):
        if stones[index_of(state, q)] == opponent(player):
            grp = get_group(_with_stones(state, stones), q)
            if len(get_liberties(_with_stones(state, stones), grp)) == 0:
                return True
    # 否则必须落子后自己有气（禁自杀）
    own = get_group(_with_stones(state, stones), point)
    return len(get_liberties(_with_stones(state, stones), own)) > 0


def _with_stones(state: GameState, stones: List[int]) -> GameState:
    s = GameState(size=state.size, stones=stones, turn=state.turn)
    return s


def place_stone(state: GameState, point: Tuple[int, int]) -> GameState:
    """落子，返回新局面（不可变）。非法着法抛 ValueError。"""
    if state.finished:
        raise ValueError("game over")
    if not in_bounds(state, point):
        raise ValueError("out of bounds")
    i = index_of(state, point)
    if state.stones[i] != 0:
        raise ValueError("occupied")
    if not is_legal_move(state, point):
        raise ValueError("illegal move")

    player = state.turn
    stones = list(state.stones)
    captured = dict(state.captured)
    ko: Optional[Tuple[int, int]] = None

    stones[i] = player
    removed: List[Tuple[int, int]] = []
    tmp = _with_stones(state, stones)
    for q in neighbors(state, point):
        if stones[index_of(state, q)] == opponent(player):
            grp = get_group(tmp, q)
            if len(get_liberties(tmp, grp)) == 0:
                for g in grp:
                    stones[index_of(state, g)] = 0
                    removed.append(g)

    # 自杀检查（place 后自己无气）
    own = get_group(_with_stones(state, stones), point)
    if len(get_liberties(_with_stones(state, stones), own)) == 0:
        raise ValueError("suicide")

    # 劫：只提一子且提后局面与提前完全相同（除落点与提点）
    if len(removed) == 1:
        victim = removed[0]
        before = state.stones
        after = stones
        identical = True
        for k in range(len(before)):
            if k == i or k == index_of(state, victim):
                continue
            if before[k] != after[k]:
                identical = False
                break
        if identical:
            ko = victim

    if player == 1:
        captured["black"] += len(removed)
    else:
        captured["white"] += len(removed)

    return GameState(
        size=state.size, stones=stones, turn=opponent(player), ko=ko,
        captured=captured, history=[*state.history, Move(player, point)],
        pass_count=0, finished=False,
    )


def pass_turn(state: GameState) -> GameState:
    """停一手。双方连续停手 → 终局。"""
    if state.finished:
        raise ValueError("game over")
    pass_count = state.pass_count + 1
    return GameState(
        size=state.size, stones=list(state.stones), turn=opponent(state.turn),
        ko=None, captured=dict(state.captured),
        history=[*state.history, Move(state.turn, None)],
        pass_count=pass_count, finished=pass_count >= 2,
    )


def undo(state: GameState) -> GameState:
    """悔一手（从历史重放重建）。"""
    if not state.history:
        return state
    s = create_board(state.size)
    for m in state.history[:-1]:
        s = place_stone(s, m.point) if m.point else pass_turn(s)
    s.history = state.history[:-1]
    return s


# ---------------------------------------------------------------------------
# 终局数子
# ---------------------------------------------------------------------------
def area_of(state: GameState) -> List[int]:
    """区域归属：每个空点属于唯一包围它的颜色（1/-1），双色包围或无边=0。"""
    owners = [0] * (state.size * state.size)
    visited = set()
    for i in range(len(state.stones)):
        if i in visited or state.stones[i] != 0:
            continue
        queue = [i]
        visited.add(i)
        region = []
        black = white = False
        while queue:
            cur = queue.pop()
            region.append(cur)
            p = (cur % state.size, cur // state.size)
            for q in neighbors(state, p):
                j = index_of(state, q)
                c = state.stones[j]
                if c == 1:
                    black = True
                elif c == -1:
                    white = True
                elif j not in visited:
                    visited.add(j)
                    queue.append(j)
        owner = 1 if (black and not white) else (-1 if (white and not black) else 0)
        for k in region:
            owners[k] = owner
    return owners


def count_score(state: GameState, method: str = "area", komi: float = 7.5) -> dict:
    """数子。method: 'area'（数空，中国规则）| 'territory'（计目，日韩规则）。"""
    owners = area_of(state)
    black = white = 0
    black_stones = white_stones = 0
    for i in range(len(state.stones)):
        if state.stones[i] == 1:
            black += 1
            black_stones += 1
        elif state.stones[i] == -1:
            white += 1
            white_stones += 1
        elif owners[i] == 1:
            black += 1
        elif owners[i] == -1:
            white += 1
    if method == "territory":
        black = black - black_stones + state.captured["black"] - state.captured["white"]
        white = white - white_stones + state.captured["white"] - state.captured["black"]
    return {"black": black, "white": white, "komi": komi, "method": method}


def winner(state: GameState, method: str = "area", komi: float = 7.5) -> int:
    """返回胜者：1 黑 / -1 白 / 0 平（需补棋时）。"""
    r = count_score(state, method, komi)
    if r["black"] - r["white"] > komi:
        return 1
    if r["white"] - r["black"] > komi:
        return -1
    return 0


# ---------------------------------------------------------------------------
# SGF
# ---------------------------------------------------------------------------
def state_to_sgf(state: GameState, komi: float = 7.5) -> str:
    moves = "".join(
        f"{'B' if m.player == 1 else 'W'}["
        + (SGF_COLS[m.point[0]] + SGF_COLS[m.point[1]] if m.point else "")
        + "]"
        for m in state.history
    )
    return f"(;GM[1]FF[4]SZ[{state.size}]KM[{komi}]{moves})"


def sgf_to_state(sgf: str) -> GameState:
    import re

    sz = re.search(r"SZ\[(\d+)\]", sgf)
    size = int(sz.group(1)) if sz else 19
    state = create_board(size)
    for m in re.finditer(r"([BW])\[([a-z]{0,2})\]", sgf):
        color = 1 if m.group(1) == "B" else -1
        p = m.group(2)
        try:
            if not p or p == "tt":
                state = pass_turn(state)
            else:
                point = (SGF_COLS.index(p[0]), SGF_COLS.index(p[1]))
                if state.turn != color:
                    state = pass_turn(state)
                state = place_stone(state, point)
        except (ValueError, IndexError):
            continue  # 非法着法跳过，继续解析
    return state
