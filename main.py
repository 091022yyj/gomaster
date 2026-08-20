#!/usr/bin/env python3
"""GoMaster 入口：AI 自动下围棋助手。

用法：
    python main.py            # 启动图形界面
    python main.py --headless # 无界面模式（需已校准的配置）

打包为 --windowed exe 后控制台不可见，运行日志写入 gomaster.log 便于排查。
"""
from __future__ import annotations

import argparse
import sys
import time

from gomaster.config import Config
from gomaster.main_loop import GoMasterLoop


def make_logger() -> "tuple":
    """返回 (on_status, on_error)：同时输出到 stdout 与 gomaster.log。"""
    import os

    # PyInstaller onefile 下 __file__ 指向临时解压目录，须用 sys.executable 定位
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base, "gomaster.log")

    def write(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    return write, write


def run_headless(cfg: Config, on_status) -> None:
    """无界面模式：自动检测棋盘并运行（适合配合已有校准）。"""
    loop = GoMasterLoop(cfg, on_status=on_status, on_state=lambda s: None)
    on_status("GoMaster 无界面模式启动（Ctrl+C 停止）")
    loop.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()
        on_status("已停止")


def main() -> None:
    parser = argparse.ArgumentParser(description="GoMaster - AI 自动下围棋助手")
    parser.add_argument("--headless", action="store_true", help="无界面模式")
    parser.add_argument("--config", default=None, help="配置文件路径（默认 exe/项目目录 gomaster_config.json）")
    args = parser.parse_args()

    on_status, _ = make_logger()
    cfg = Config.load(args.config)
    if args.headless:
        run_headless(cfg, on_status)
        return

    # 图形界面
    try:
        import tkinter as tk
        from gomaster.gui import GomasterGUI
    except Exception as e:
        on_status(f"无法启动图形界面（{e}），请使用 --headless 或安装 Tkinter")
        sys.exit(1)

    root = tk.Tk()
    app = GomasterGUI(root, cfg)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
