"""
KataGo GTP 客户端：子进程启动引擎，通过 GTP 协议通信。
支持 boardsize / play / genmove / kata-analyze（流式）。
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple


def parse_info_lines(lines: List[str], max_candidates: int = 5) -> List[Dict]:
    """解析 kata-analyze 输出的 info 行，按 move 去重取最新快照，按胜率排序。

    每个候选含：move / visits / winrate / scoreLead / pv（变化图，可能为空）。
    """
    seen: Dict[str, Dict] = {}
    for line in lines:
        if not line.startswith("info"):
            continue
        for m in re.finditer(
            r"move\s+(\w+)\s+.*?visits\s+(\d+)\s+.*?winrate\s+([\d.]+)\s+.*?scoreLead\s+([-\d.]+)"
            r"(?:\s+.*?pv\s+(.*))?$",
            line,
        ):
            move, visits, wr, sl = (m.group(1), int(m.group(2)),
                                    float(m.group(3)), float(m.group(4)))
            pv = (m.group(5) or "").strip().split()[:12]  # 前 12 手变化图
            if move not in seen or visits > seen[move]["visits"]:
                seen[move] = {"move": move, "visits": visits,
                              "winrate": wr, "scoreLead": sl, "pv": pv}
    cands = sorted(seen.values(), key=lambda c: -c["winrate"])
    return cands[:max_candidates]


class KataGoClient:
    def __init__(self, engine_path: str, model_path: str, config_path: str = "",
                 rules: str = "chinese", komi: float = 7.5,
                 num_search_threads: int = 64):
        self.engine_path = engine_path
        self.model_path = model_path
        self.config_path = config_path
        self.rules = rules
        self.komi = komi
        self.num_search_threads = num_search_threads
        self.proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._ready = False

    def start(self, board_size: int = 19) -> None:
        """启动引擎并初始化棋盘。"""
        if self.proc and self.proc.poll() is None:
            return
        cmd = [self.engine_path, "gtp", "-model", self.model_path]
        if self.config_path:
            cmd += ["-config", self.config_path]
        # 强制搜索线程数：配置文件里过大的 numSearchThreads 会导致
        # kata-analyze 几乎不搜索（visits 停滞在 1，胜率显示 0%）
        cmd += ["-override-config", f"numSearchThreads={self.num_search_threads}"]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        # 等待引擎就绪（KataGo 启动需 10-40 秒，GPU 初始化）
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                resp = self.command("name", timeout=10)
                if resp and "error" not in resp.lower():
                    break
            except Exception:
                pass
            time.sleep(2)
        self.command(f"boardsize {board_size}")
        self.command("clear_board")
        self.command(f"komi {self.komi}")
        self._ready = True

    def command(self, cmd: str, timeout: float = 30.0) -> str:
        """发送单条 GTP 命令，返回响应正文（去掉 '= ' 前缀）。"""
        if not self.proc or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("引擎未启动")
        with self._lock:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
            lines: List[str] = []
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise RuntimeError("引擎进程退出")
                line = line.rstrip("\n")
                if not line:  # GTP 空行 = 响应结束
                    break
                if line.startswith("="):
                    lines.append(line[1:].strip())
                elif line.startswith("?"):
                    raise RuntimeError("GTP error: " + line[1:].strip())
                else:
                    lines.append(line)
            return "\n".join(lines)

    def play(self, color: str, point: str) -> None:
        """落子：play B Q16 / play B pass"""
        self.command(f"play {color} {point}")

    def genmove(self, color: str, timeout: float = 60.0) -> str:
        """让引擎走一步，返回 GTP 坐标（如 Q16）或 pass/resign。"""
        resp = self.command(f"genmove {color}", timeout=timeout)
        return resp.strip()

    def analyze(self, color: str, seconds: float = 5.0, max_candidates: int = 5
                ) -> Tuple[List[Dict], Dict]:
        """分析当前局面（kata-analyze 流式协议），不改变引擎棋盘。

        返回 (候选列表, 汇总)。候选: [{move, visits, winrate, scoreLead}]
        """
        if not self.proc or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("引擎未启动")
        with self._lock:
            self.proc.stdin.write(f"kata-analyze {color} {seconds}\n")
            self.proc.stdin.flush()
            # 关键：分析期间必须持续读取 stdout，否则管道缓冲填满会阻塞引擎搜索
            lines: List[str] = []
            done = threading.Event()

            def reader() -> None:
                while not done.is_set():
                    line = self.proc.stdout.readline()
                    if not line:  # 引擎退出
                        break
                    line = line.rstrip("\n")
                    if not line:  # 空行 = 响应结束
                        break
                    if line.startswith("?"):
                        break
                    lines.append(line)

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            time.sleep(seconds + 0.5)
            self.proc.stdin.write("\n")  # 空行结束分析
            self.proc.stdin.flush()
            t.join(timeout=10)
            done.set()
            if t.is_alive():
                # 引擎未在超时内结束分析（异常）：杀掉进程并清状态，
                # 避免 reader 线程阻塞在 readline 上污染下一次 analyze 的输出
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
                except Exception:
                    pass
                self._ready = False
                self.proc = None
                raise RuntimeError("分析超时：引擎未响应")
        cands = parse_info_lines(lines, max_candidates)
        if not cands:
            return [], {"winrate": 0.5, "scoreLead": 0.0, "best": "pass"}
        best = cands[0]
        return cands, {"winrate": best["winrate"], "scoreLead": best["scoreLead"],
                       "best": best["move"]}

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write("quit\n")
                self.proc.stdin.flush()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
        self.proc = None
        self._ready = False
