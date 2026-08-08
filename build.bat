@echo off
chcp 65001 >nul
REM ============================================================
REM GoMaster 一键打包 exe（Windows）
REM 用法：双击 build.bat，或在 cmd 中运行
REM 产物：dist\GoMaster.exe
REM ============================================================
title GoMaster 打包

echo [1/4] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo 未找到 Python，请先安装 Python 3.8+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)

echo [2/4] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
)

echo [3/4] 安装 PyInstaller...
pip install pyinstaller
if errorlevel 1 (
    echo PyInstaller 安装失败
    pause
    exit /b 1
)

echo [4/4] 打包 exe（约 1-3 分钟）...
pyinstaller --noconfirm --onefile --windowed ^
    --name GoMaster ^
    --collect-all mss ^
    --collect-all cv2 ^
    --collect-all PIL ^
    --collect-all pyautogui ^
    main.py
if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)

echo.
echo ============================================================
echo 打包完成：dist\GoMaster.exe
echo 首次运行请填写 KataGo 引擎/模型路径（见 README）
echo ============================================================
pause
