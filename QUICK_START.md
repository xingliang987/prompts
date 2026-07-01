# Robot Pi0.5 Pipeline — Quick Start

## 系统架构

```
本机 (spark-adaf, Docker pi)
  ├── robot_client.py ───WebSocket──→ 192.168.127.24:8765
  │                                    ├── robot_server.py
  │                                    ├── ROS2 + MoveIt
  │                                    ├── Gemini 335L (正面相机)
  │                                    └── Gemini 305 (夹爪相机)
  │
  ├── WebUI (collect_data_web.py)       http://localhost:8081
  └── Web Monitor (web_monitor.py)      http://localhost:8080
```

## 关键文件

| 文件 | 位置 | 作用 |
|------|------|------|
| robot_client.py | /opt/workspace/ | LeRobot 客户端, 实现 Robot 协议 |
| collect_data.py | /opt/workspace/ | VR 数据采集脚本 (CLI) |
| **collect_data_web.py** | **/opt/workspace/** | **WebUI 采集控制（推荐）** |
| robot_server.py | /opt/workspace/ | 远程桥接服务源码 (运行在 ROBOT_HOST) |
| hand_grasp_server.py | /opt/workspace/ | 灵巧手服务 (运行在 ROBOT_HOST) |
| web_monitor.py | /opt/workspace/ | Web 监控界面（已集成到 WebUI 中） |
| **start_collect_web.sh** | **/home/telecontrol/** | **WebUI 宿主机管理脚本** |
| hardware_prepare.sh | ~/Desktop/DataCollection/ | 一键硬件准备脚本 |
| teleop_prepare.sh | ~/Desktop/DataCollection/ | 遥操作环境脚本 |

## 环境变量

```bash
export ROBOT_HOST=192.168.127.24   # 远程机械臂 IP
```

## 启动方式（推荐）

```bash
# 第一步：远程机械臂 (SSH 到 ROBOT_HOST)
bash /home/sunrise/Desktop/testing/teleop_launch_scripts/terminal1.sh
# 等待 30-40s 关节初始化

# 第二步：远程启动 WebSocket 桥接 (新开 SSH)
source /opt/ros/humble/setup.bash
source /home/sunrise/ros2_ws/install/setup.bash
source /home/sunrise/calibration_ws/install/setup.bash
python3 /home/sunrise/robot_server.py --port 8765

# 第三步：打开 WebUI 采集 (本机浏览器)
#   http://localhost:8081
#   → Connect → Start → Stop → Finish
```

## 传统 CLI 数据采集

```bash
# 容器内执行
docker exec pi bash -lc '
  cd /opt/workspace
  /opt/workspace/openpi/.venv/bin/python collect_data.py \
    --host 192.168.127.24 --port 8765 \
    --episodes 50 --episode-time 30 --fps 10 \
    --task "pick up the red cube"
'
```

## 启动顺序 (远程机械臂)

```
1. 远程: bash teleop_launch_scripts/terminal1.sh (CAN + ROS 控制, 等 30s)
2. 远程: python3 robot_server.py (WebSocket :8765)
3. 本机: http://localhost:8081 (WebUI 采集)
```

或使用一键脚本：
```bash
~/Desktop/DataCollection/hardware_prepare.sh
# 或 (遥操作模式):
~/Desktop/DataCollection/teleop_prepare.sh
```

## 维度

- state_dim = 8: [L1~L7 弧度, gripper(0~1)]
- action_dim = 8: [L1~L7 弧度, gripper(0~1)]
- Images: 640x480 RGB (front + wrist)
- gripper: hand_state[0]/255.0 (0=闭合, 1=张开), 硬件读数

## 已知问题

- 采集帧率约 1.5-2 fps（受 robot_server JPEG 传输限制）
- Stop 后显示 "recording" 是正常的（AV1 编码中，10帧约5s）
- Start 后需等 5-15s 数据集创建 + 15-20s 预热
