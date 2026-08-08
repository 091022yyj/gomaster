# GoMaster - AI 自动下围棋助手

在 **腾讯围棋 / 野狐围棋** 上辅助下棋：屏幕识别棋盘 → KataGo 分析 → 
**两种模式**：
- 🖐 **手动模式**：透明悬浮窗叠加在棋盘上，实时显示 AI 推荐落点 + 每个候选点的胜率（胜率越高越红越大），你自己落子
- 🤖 **全自动模式**：AI 自动点击落子，全程无人值守

两个模式共用分析面板：胜率/目差曲线、AI 推荐、变化图（PV）、复盘报告、对局记录、战绩统计、SGF 导出。

> ⚠️ 技术用于学习交流，请勿在正式对局中作弊。

## 原理（与文档思路一致）

```
┌──────────┐  截图   ┌──────────────┐  局面   ┌──────────────┐
│ 屏幕/窗口 │ ─────▶ │ GBR 棋盘识别   │ ─────▶ │ KataGo 引擎   │
│ (腾讯/野狐)│        │ (OpenCV)     │        │ (分析/推荐)   │
└──────────┘        └──────────────┘        └──────┬───────┘
      ▲                                            │ GTP 坐标
      │ 模拟点击（全自动）/ 悬浮窗提示（手动）        ▼
      └───────────────────────── ┌──────────────┐
                                 │ 自动落子      │
                                 │ (pyautogui)  │
                                 └──────────────┘
```

1. **屏幕捕捉**（mss）：定时截取全屏
2. **GBR 棋盘识别**（OpenCV）：
   - 自动检测棋盘外框（HSV 木色过滤 + Canny 边缘回退），失败可手动点 4 角校准
   - 透视变换拉正 + 网格扫描，自适应亮度判定黑白 → 19 路局面数组 + GTP 坐标（Q16、D4）
3. **轮到谁**：轮次跟踪（不依赖 OCR）——对比前后帧发现"新出现的棋子"即对手落子，自然切换轮次；支持执黑/执白/自动
4. **KataGo 分析**：子进程 GTP 协议通信，可配思考时间/胜率/目差/变化图
5. **自动落子**（全自动）：棋盘坐标 → 屏幕像素 → pyautogui 模拟点击
6. **悬浮窗**（手动）：透明置顶窗口叠加在棋盘上方，圆点 + 胜率百分比 + 闪烁推荐圈

## 快速开始

### 方式一：源码运行（开发调试）
```bash
pip install -r requirements.txt
python main.py
```

### 方式二：打包成 exe（Windows）
1. 把整个项目复制到 Windows 电脑
2. 安装 [Python 3.8+](https://www.python.org/downloads/)（勾选 Add to PATH）
3. 双击 `build.bat`，等待完成 → 生成 `dist\GoMaster.exe`
4. 双击 `GoMaster.exe` 运行

## 使用步骤

1. 打开腾讯围棋/野狐围棋，进入对局（**窗口保持可见**）
2. 启动 GoMaster，选择模式（🖐 手动 / 🤖 全自动），填写：
   - **KataGo 路径**：如 `C:\katago\katago.exe`
   - **模型路径**：如 `C:\katago\model.bin.gz`（b40c768 或 b28c512 均可）
   - **思考秒数**：推荐 5-15 秒（文档配置 11.5s）
   - **执棋**（全自动）：auto / B（执黑）/ W（执白）
3. 点「📷 刷新截图」→ 在预览图上点击棋盘 **4 个角**（左上→右上→右下→左下），或点「🎯 自动检测棋盘」
4. 点「✓ 校准完成」→「▶ 开始」
   - **手动模式**：悬浮窗会叠在棋盘上显示推荐落点和各点胜率，你在游戏里自己点
   - **全自动模式**：AI 自动落子，观察日志和面板即可
5. 对局中随时看右侧面板的胜率曲线/变化图；结束后点「📥 导出 SGF」或「🏆 战绩」

> 💡 悬浮窗透明背景依赖 Windows `-transparentcolor`（自动启用）；若显示黑底属正常兜底（其他平台），可关掉"悬浮窗坐标"减少干扰。

## KataGo 引擎准备（Windows）

1. 下载 KataGo v1.15.3 Windows 版：https://github.com/lightvector/KataGo/releases
2. 下载模型（任选其一）：
   - b40c768（强，需 GPU）：https://kata.gosquares.net/
   - b28c512（文档配置，M1 也能跑）：https://kata.gosquares.net/
3. 建议配置 `gtp_fast.cfg`（可参考 `examples/gtp_example.cfg`）：
   ```
   numSearchThreads = 32
   maxVisits = 10000
   maxTime = 15
   lagBuffer = 0.1
   ```
   > ⚠️ `numSearchThreads` 不要设过大（如 256）。部分显卡下过大的线程数会导致
   > `kata-analyze` 搜索停滞（胜率显示 0%、建议着法乱跳）。程序启动时会强制覆盖为
   > 64（可在 `gomaster_config.json` 中调整 `num_search_threads`）。

## 常见问题

- **识别不准**：重新校准 4 角；确保棋盘在屏幕中完整可见、无窗口遮挡
- **点击位置偏**：校准角点要精确点在棋盘最外沿交叉点中心
- **exe 被杀毒拦截**：PyInstaller 单文件程序常被误报，添加白名单即可
- **无界面模式**：`python main.py --headless`（配合已保存的配置）

## 项目结构

```
gomaster/
├── main.py                  # 入口（GUI / --headless）
├── gomaster/
│   ├── board_recognition.py # GBR 棋盘识别（自动检测/手动校准/棋子识别）
│   ├── katago_client.py     # KataGo GTP 客户端
│   ├── main_loop.py         # 主循环（轮次跟踪/AI 决策）
│   ├── autoplayer.py        # 自动落子（pyautogui）
│   ├── capture.py           # 屏幕捕捉（mss）
│   ├── config.py            # 配置持久化
│   └── gui.py               # Tkinter 界面
├── tests/                   # 单元测试（pytest）
├── build.bat                # Windows 一键打包 exe
└── requirements.txt
```

## 免责声明

本项目仅供学习研究 OpenCV 图像识别与 KataGo 集成。请勿用于线上对局作弊。
