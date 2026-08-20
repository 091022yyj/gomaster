#!/usr/bin/env bash
# ============================================================
# GoMaster 一键打包 app（macOS）
# 用法：bash build-macos.sh
# 产物：dist/GoMaster.app
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/4] 检查 Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3，请先安装 Python 3.9+（brew install python 或 python.org）"
    exit 1
fi
python3 --version

echo "[2/4] 安装依赖..."
python3 -m pip install -r requirements.txt

echo "[3/4] 安装 PyInstaller..."
python3 -m pip install pyinstaller

echo "[4/4] 打包 app（约 1-3 分钟）..."
# 用目录模式而非 --onefile：onefile 的 .app 每次启动都要解压，冷启动要十几秒
python3 -m PyInstaller --noconfirm --windowed \
    --name GoMaster \
    --osx-bundle-identifier com.gomaster.app \
    --collect-all mss \
    --collect-all cv2 \
    --collect-all PIL \
    --collect-all pyautogui \
    main.py

cat <<'EOF'

============================================================
打包完成：dist/GoMaster.app

首次运行前请到「系统设置 → 隐私与安全性」授权：
  · 屏幕录制    —— 否则截图只拍到壁纸，识别不到棋盘
  · 辅助功能    —— 否则自动落子时鼠标不动
授权后需要完全退出 App 再重开才生效。

引擎与模型路径在设置页填写（见 README）。
============================================================
EOF
