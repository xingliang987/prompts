# Development Log

## 项目说明

机器人数据采集 & pi0.5 VLA 全链路：
7-DoF 左臂 + LinkerHand 夹爪，WebSocket 桥接 ROS2 Humble 远程控制机器。
NVIDIA Thor GPU 训练，Orbbec 双目相机采集。

## 操作记录

### 2026-07-01

- **初始化 Git 仓库**：在工作区根目录执行 `git init`，创建版本管理。
- **创建 `.gitignore`**：排除 `__pycache__/`、`.venv/`、`data/`、`checkpoints/`、`logs/`、`*.bak`、`forward_*.py` 等运行时生成和临时文件，避免将大文件或环境无关文件纳入版本控制。
