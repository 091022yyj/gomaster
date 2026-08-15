# gomaster

Windows 围棋 AI 助手：OpenCV 屏幕识别棋盘 → 本地 KataGo 分析 → 透明悬浮窗提示最佳选点，还能全自动点击帮你落子。现有围棋 AI 工具没有透明悬浮窗叠加、更没有全自动落子——gomaster 是第一个把两者同时做出来的。

![Version](https://img.shields.io/github/v/release/091022yyj/gomaster)
![License](https://img.shields.io/github/license/091022yyj/gomaster)
![Language](https://img.shields.io/badge/Language-Python-3776AB)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📷 屏幕识别 | OpenCV 自动识别棋盘局面，打开对局即用 |
| 🧠 KataGo 分析 | 本地引擎，秒级输出胜率与推荐选点 |
| 🪟 透明悬浮窗 | 分析结果悬浮叠加在对局窗口上，不遮挡棋盘 |
| 🤖 全自动落子 | 手动提示 / 全自动点击两种模式，可调落子延迟 |
| 🎮 平台适配 | 支持腾讯围棋、野狐围棋 |
| ⚙️ 参数可调 | 自定义识别区域、引擎参数、落子节奏 |

## 📸 截图

| 悬浮窗提示 | 参数设置 | 自动落子模式 |
|------------|----------|--------------|
| ![悬浮窗](docs/screenshot-overlay.png) | ![设置](docs/screenshot-settings.png) | ![自动模式](docs/screenshot-auto.png) |

## 🚀 快速开始

Windows 用户：
1. 从 Releases 下载 `gomaster-setup.exe` 并安装
2. 下载 KataGo 模型权重，在设置页指定路径
3. 打开对局窗口，点击"识别棋盘"

源码运行：

```bash
git clone https://github.com/091022yyj/gomaster.git
cd gomaster
pip install -r requirements.txt
python main.py
```

## ❓ FAQ

**Q: 需要自己安装 KataGo 吗？**
A: 引擎已内置，只需在设置页指定模型权重文件路径即可。

**Q: 会被对弈平台判定违规吗？**
A: 本工具只做屏幕识别与模拟点击；请先了解并遵守对应平台规则，自行评估使用风险。

**Q: 支持窗口化（非全屏）对局吗？**
A: 支持，可手动框选识别区域，1080p 以上分辨率体验最佳。

**Q: 自动模式怎么控制节奏？**
A: 设置里可调落子延迟（0.5s – 10s），避免点击过快被识别为异常操作。

## 🏷️ 推荐 Topics

`go` `weiqi` `baduk` `katago` `opencv` `ai-assistant` `windows` `board-game`
