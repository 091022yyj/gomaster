"""端到端验证：合成截图驱动主循环 → 识别 → 轮次跟踪 → 真实 KataGo 分析 → 落子。

截图基于 loop.state 渲染：对手按时序落子，AI 落子后本地 state 更新，
下一帧截图即包含 AI 的子 → 识别确认 → 完整闭环。
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from gomaster.board_recognition import render_synthetic_board, BoardModel
from gomaster.config import Config
from gomaster.main_loop import GoMasterLoop

KATAGO = os.path.expanduser("~/katago/v1.15.3/katago")
MODEL = os.path.expanduser("~/katago/model.bin.gz")
CFG = os.path.expanduser("~/katago/gtp_fast.cfg")

# 模拟对局：对手执黑依次落子（每 12 秒一手）
opponent_moves = [(3, 3), (16, 3), (3, 16)]
t0 = time.time()


def main():
    if not (os.path.exists(KATAGO) and os.path.exists(MODEL)):
        print("SKIP: 未找到 KataGo 引擎/模型")
        return
    logs = []
    cfg = Config(katago_path=KATAGO, model_path=MODEL, config_path=CFG,
                 think_seconds=2.0, my_color="W", auto_click=False, interval=0.5)
    loop = GoMasterLoop(cfg, on_status=logs.append)

    def screenshot():
        elapsed = time.time() - t0
        n = min(len(opponent_moves), int(elapsed / 12) + 1)
        stones = [(1, x, y) for x, y in opponent_moves[:n]]
        # AI 已落的子（本地同步在 loop.state 中）也渲染出来
        for y in range(loop.state.shape[0]):
            for x in range(loop.state.shape[1]):
                if loop.state[y, x] == -1:  # 我方白子
                    stones.append((-1, x, y))
        return render_synthetic_board(19, stones)

    loop.screenshot_fn = screenshot
    # 用合成图校准棋盘
    img = render_synthetic_board(19, [])
    h, w = img.shape[:2]
    m = 25
    loop.set_board(BoardModel(19, [(m, m), (w - m, m), (w - m, h - m), (m, h - m)]))
    loop.start()
    try:
        # 对手 3 手（每 12 秒）+ AI 应手
        time.sleep(85)
    finally:
        loop.stop()
    print("===== 日志 =====")
    for l in logs:
        print(" ", l)
    rec = [l for l in logs if "AI 推荐" in l]
    click = [l for l in logs if "建议落子" in l]
    ok = len(rec) >= 2 and len(click) >= 2
    print(f"===== AI 推荐 {len(rec)} 次, 建议落子 {len(click)} 次")
    print("===== 结果:", "通过 ✅" if ok else "失败 ❌")


if __name__ == "__main__":
    main()
