# CLAUDE.md — 机器人数据采集 & pi0.5 VLA pipeline（完整文档）

## 项目概述
pi0.5 VLA 全链路：数据采集 → 模型微调 → 部署推理。
7-DoF 左臂 + LinkerHand 夹爪，通过 WebSocket 桥接 ROS2 Humble 远程控制机器。
NVIDIA Thor GPU 训练，Orbbec 双目相机采集。

---

## 快速开始

### 30 秒速览

```bash
# 1. 查看所有服务状态
bash /home/telecontrol/workspace/start_all.sh status

# 2. 启动推理 WebUI（不依赖机器人，立即可用）
bash /home/telecontrol/workspace/start_all.sh inference start
# → 浏览器打开 http://localhost:8090，输入 prompt 点击「推理」

# 3. 启动数据采集 WebUI（依赖机器人连接）
bash /home/telecontrol/workspace/start_all.sh data-collection start
# → 浏览器打开 http://localhost:8081

# 4. 启动远程机器人服务（需 SSH 到远程机器）
bash /home/telecontrol/workspace/start_all.sh remote start

# 5. 停止一切
bash /home/telecontrol/workspace/start_all.sh stop
```

### 前置条件

| 条件 | 说明 |
|------|------|
| Docker 容器 `pi` 正在运行 | `docker ps` 确认，否则 `docker start pi` |
| 远程机器人电源开启 | 机械臂上电，CAN 总线正常 |
| 远程机器网络可达 | `ping ${ROBOT_HOST}`（默认 192.168.31.11） |
| SSH 免密 | `sshpass -p 'sunrise' ssh sunrise@${ROBOT_HOST}` |

## 硬件

| 设备 | 位置 | 说明 |
|------|------|------|
| 本机（原 spark-adaf 迁移至此） | /home/telecontrol | Docker pi 容器运行采集 WebUI，通过 SSH 访问远程 |
| ROBOT_HOST (远程) | sunrise@192.168.127.24 / sshpass -p 'sunrise' | 机械臂控制 + ROS2 + CAN |
| 机械臂 | 远程 | 7-DoF 左臂 (L1~L7) + 右臂 (R1~R7, 不用) |
| 夹爪 | 远程 | LinkerHand, SDK 通过 can0 通信 |
| 正面相机 | 远程, USB3 | Orbbec Gemini 335L, namespace `/camera` |
| 夹爪相机 | 远程, USB2 | Orbbec Gemini 305, namespace `/camera_wrist` |
| CAN 总线 | 远程 | can0 + can1, 1Mbps, 两个都必须要 |

### 端口与服务一览

| 端口 | 服务 | 位置 | 说明 |
|------|------|------|------|
| 8081 | 数据采集 WebUI (HTTP) | 本机 → Docker | Web 页面，浏览器访问 |
| 8082 | 数据采集 WebUI (WS) | 本机 → Docker | WebSocket 控制通道 |
| 8090 | 推理监测 WebUI | 本机 → Docker | 独立推理界面 |
| 8765 | robot_server | 远程 | 机器人 WebSocket 桥接 |
| 22 | SSH | 远程 | 远程机器管理 |

所有本机端口通过 `start_all.sh` 的 TCP forwarder 映射到 Docker 容器内部。

## 关键文件

### 本机 (/home/telecontrol/workspace/ + Docker pi:/opt/workspace/)
- `collect_data_web.py` — WebUI 数据采集控制（容器内 `/opt/workspace/collect_data_web.py`）
- `robot_client.py` — LeRobot Robot 协议的 WebSocket 客户端
- `start_collect_web.sh` — 宿主机一键管理脚本（启停 + 端口转发）
- `can_joint_pub.py` — CAN 总线→关节数据解码器源码（同步到远程 `/tmp/can_joint_pub.py`）
- `hand_state_pub.py` — LinkerHand SDK 发布器源码（同步到远程 `/tmp/hand_state_pub.py`）
- `data_collection_guide.md` — 完整启动流程文档
- `TELEOP_GUIDE.md` — 遥操作启动步骤（terminal1-5）
- `fix_cameras.sh` — 远程相机启动脚本
- `inference_webui.py` — 推理监测 WebUI（容器内 `/opt/workspace/inference_webui.py`）
- `start_all.sh` — **全组件统一管理脚本**（代替 `start_collect_web.sh`）
- `CLAUDE.md` — 本文件

### 远程 (/home/sunrise/ + /tmp/)
- `/home/sunrise/robot_server.py` — WebSocket 桥接服务（v2: 从文件读关节数据）
- `/tmp/can_joint_pub.py` — CAN 总线→关节数据解码器（无 rclpy）
- `/tmp/hand_state_pub.py` — LinkerHand SDK → 灵巧手状态
- `/home/sunrise/ros2_ws/` — ROS2 工作空间 (grasp_bringup, arm_moveit, arm_hardware)
- `/home/sunrise/calibration_ws/` — 电机标定参数/关节限位
- `/home/sunrise/vision_ws/` — Orbbec 相机驱动

## 远程 IP 配置

所有代码通过 `ROBOT_HOST` 环境变量读取远程 IP，默认 `192.168.127.24`：
```bash
export ROBOT_HOST=192.168.127.24
```
也可直接传参 `--host` 或 `NetworkRobot("ip", 8765)`。

## 系统架构

### 完整网络拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│ 本机 (telecontrol)                                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ start_all.sh (管理脚本)                                    │   │
│  │   inference start/stop                                    │   │
│  │   data-collection start/stop                              │   │
│  │   remote start/stop (SSH 到远程)                          │   │
│  │   status / logs                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Host Ports ← TCP Forwarders → Docker Container (pi)             │
│  ┌────────────┐    ┌──────────────┐                              │
│  │ :8081 (HTTP)│───▶│ collect_data │  Data Collection WebUI      │
│  │ :8082 (WS)  │───▶│ _web.py      │  (http://localhost:8081)   │
│  ├────────────┤    └──────────────┘                              │
│  │ :8090 (HTTP)│───▶│ inference_    │  Inference WebUI            │
│  │             │    │ webui.py     │  (http://localhost:8090)    │
│  └────────────┘    └──────┬───────┘                              │
│                           │ pi0.5 model (checkpoint 199)        │
│                           └────────────────────────────────────── │
│                                                                  │
│  Browser WS2 ──WebSocket──→ 远程 robot_server:8765 (监控直连)    │
└─────────────────────────────────────────────────────────────────┘
                           │ SSH (sshpass)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 远程机器人 (sunrise@ROBOT_HOST:192.168.31.11)                    │
│  ┌──────────────┐    ┌──────────────────┐                       │
│  │ can_joint_   │───▶│ /tmp/joint_      │──▶ robot_server      │
│  │ pub.py       │    │ positions.json   │    :8765              │
│  │ (CAN→关节)   │    └──────────────────┘    (WebSocket 桥接)   │
│  └──────┬───────┘                           ┌──────────────┐   │
│         │ can0                              │ CameraCache  │   │
│         ▼                                   │ (rclpy 线程) │   │
│  ┌──────────────┐                           └──────────────┘   │
│  │ ros2_control │─── ros2 topics ──────▶  /camera/.../compressed│
│  │ _node (teleop)│  (可选启动)              /hand_state          │
│  └──────────────┘                           │                    │
│  ┌──────────────┐    ┌──────────────┐       │                    │
│  │ hand_state_  │───▶│ /hand_state  │───────┘                    │
│  │ pub.py       │    │ (Int32Multi  │                            │
│  │ (SDK→ROS2)   │    │  Array)      │                            │
│  └──────┬───────┘    └──────────────┘                            │
│         │ can0 (LinkerHand)                                      │
│         ▼                                                        │
│  ┌──────────────┐    ┌──────────────┐                            │
│  │ Gemini 335L  │───▶│ /camera/.../ │──▶ camera_writer.py        │
│  │ (正面, USB3) │    │ compressed   │    (JPEG→/tmp/camera_*.jpg)│
│  └──────────────┘    └──────────────┘                            │
│  ┌──────────────┐    ┌──────────────┐                            │
│  │ Gemini 305   │───▶│ /camera_wrist│                            │
│  │ (夹爪, USB2) │    │ /.../compressed│                           │
│  └──────────────┘    └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### WebUI 通信架构

```
浏览器 (用户)
  ├── WS1 → localhost:8082 → DataCollector (采集控制: Connect/Start/Stop/Finish)
  └── WS2 → robot_host:8765 → robot_server (监控: get_observation, 100ms 轮询)

推理 WebUI (独立于采集)
  ├── HTTP → localhost:8090 (页面 + API)
  └── SSE  → /events (模型状态推送)
```

### 关节数据独立于 ros2_control_node — `can_joint_pub.py` 直接从 CAN 总线解码 MIT 协议反馈帧，不创建 rclpy 节点，不和 teleop 抢 DDS 资源。

## 启动顺序（数据采集模式）

一键启动：
```bash
bash /home/telecontrol/workspace/start_data_collection.sh
```

或分步（推荐不依赖 teleop 的最小服务集）：
```bash
# 远程: 1. 相机（先 335L 后 305，顺序重要）
source /opt/ros/humble/setup.bash && source /home/sunrise/vision_ws/install/setup.bash
ros2 launch orbbec_camera gemini_330_series.launch.py camera_name:=camera serial_number:=CP2G853000G1 enable_point_cloud:=false enable_depth:=true depth_width:=640 depth_height:=480 color_width:=640 color_height:=480 color_fps:=10 depth_fps:=10
# 等 10s 后
ros2 launch orbbec_camera gemini305.launch.py camera_name:=camera_wrist enable_point_cloud:=false enable_depth:=false color_width:=640 color_height:=480 color_fps:=10

# 远程: 2. CAN 关节解码器（从 can0 读 MIT 帧，无 rclpy）
python3 /tmp/can_joint_pub.py &

# 远程: 3. 灵巧手 SDK
source /opt/ros/humble/setup.bash && source /home/sunrise/ros2_ws/install/setup.bash && source /home/sunrise/calibration_ws/install/setup.bash
python3 /tmp/hand_state_pub.py &

# 远程: 4. WebSocket 桥接
python3 /home/sunrise/robot_server.py --port 8765

# 本机: 5. WebUI 采集
# 浏览器 http://localhost:8081 → Connect → Start/Stop/Finish
```

如需遥操作，按 `TELEOP_GUIDE.md` 启动（teleop 和采集互不干扰，因为采集用 CAN 解码不抢 DDS）。

## 数据采集

### WebUI 采集步骤
1. 浏览器打开 `http://localhost:8081`
2. 在 Task 输入框粘贴 prompt（参考下方列表）
3. 点击 **Connect**（连接远程机器人）
4. 点击 **Start** → 3s 预热 → 自动录制
5. 操控机械臂执行任务
6. 点击 **Stop** → 后台编码保存当前 episode
7. 重复 4-6 采集多个 episodes
8. 全部完成点击 **Finish**

### 推荐 prompts
```
pick up the red cube
place the red cube on the tray
pick up the blue cylinder
put the blue cylinder into the box
pick up the screwdriver from the table
hand me the pliers
push the button on the panel
turn the knob clockwise
grasp the sponge and wipe the board
pick up the green block and stack it on the yellow block
```

### 数据格式
每个 session 存为一个 LeRobot 数据集（`/workspace/data/dataset_<timestamp>/`），多个 episodes 共用同一个 task：

| 字段 | 维度 | 说明 |
|------|------|------|
| `observation.images.front` | 480×640×3 video | 正面 335L 相机 |
| `observation.images.wrist` | 480×640×3 video | 夹爪 305 相机 |
| `observation.state` | float32 [8] | L1~L7 弧度 + gripper(0~1) |
| `action` | float32 [8] | L1~L7 弧度 + gripper(0~1) |
| `task` | str | task prompt |

### 注意
- Start 后需要等 5-15s 数据集创建 + 3s 预热
- Stop 后显示 "recording" 是正常的——后台在编码 AV1 视频
- 分辨率默认为 320×240（可在 WebUI 切换），640×480 帧率约 1.5-2fps
- Cam 模式可选 Dual（前+腕）或 Front Only（仅正面）
- 每个 session 仅一个 task，换 task 需 Finish 后重新 Start


## WebSocket 协议

### 请求 (JSON 文本帧)
```json
{"type": "get_observation"}              # 读状态+图像
{"type": "send_action", "joint_positions": [...], "gripper": 0.0}  # 发动作
{"type": "hand_action", "command": "open|close"}
{"type": "get_info"}                     # 机器人信息
{"type": "stop"}                         # 紧急停止
```

### 响应
- `get_observation` → JSON 元数据帧（含 has_front_image / has_wrist_image）+ 两帧 JPEG 二进制
- `send_action` → JSON action_result
- 关节数据: 7 个 L1~L7 弧度值
- image: 640x480 RGB, JPEG 编码

### 动作/状态维度
- state_dim = 8 (L1_joint ~ L7_joint + gripper, 关节弧度, gripper 0~1)
- action_dim = 8 (7 关节 + 1 夹爪)
- gripper 值来自 `hand_state[0]/255`（SDK 硬件读数，0=闭合 255=张开）

### LinkerHand 灵巧手
- SDK 通过 can0 通信，`LinkerHandApi(hand_joint="O6", hand_type="left", can="can0")`
- **二值控制**：0.0=张开, >0.0=闭合（无死区，只有全开/全关两个状态）
- `get_state()` 返回 6 维数组 (0~255)，首值为当前手指位置
- `/execute_hand_grasp` 服务因 `rosidl_typesupport_c` 缺失不可用；手部控制走 SDK 直接通信

## ROS2 服务接口

| 服务 | 类型 | 用途 |
|------|------|------|
| /execute_motion_step | grasp_bringup/srv/ExecuteMotionStep | 执行关节动作 (timeout ~20s) |
| /execute_hand_grasp | grasp_bringup/srv/ExecuteHandGrasp | 夹爪控制, 字段 "grasp_type" + "arm_side" |
| /stop_motion | grasp_bringup/srv/StopMotion | 停止运动 |

## 关键技术决策

### robot_server.py 缓存架构
- **服务调用**（send_action）使用 `ros2 service call` CLI 子进程，避免了 rclpy 长连接内存泄漏
- **状态/图像读取**（get_observation）使用 rclpy 后台缓存线程（`CameraCache`）：
  - 单线程 + SingleThreadedExecutor，订阅 `/camera/.../compressed`、`/hand_state`
  - 关节数据通过文件 `/tmp/joint_positions.json` 读取（由 `can_joint_pub.py` 写入），不使用 rclpy 订阅，避免与 teleop 的 DDS 冲突
  - `hand_state` 由 `hand_state_pub.py` 以 20Hz 发布 6 维 Int32MultiArray (0~255)
  - rclpy 订阅头几帧可能触发 FastDDS 刷屏报错，不影响功能
- 内存占用稳定 ~70MB（未触发 11GB 泄漏问题）

### 关节数据解析
- `can_joint_pub.py` 从 can0 解码 MIT 协议反馈帧，写入 `/tmp/joint_positions.json`
- `robot_server.py` (v2) 直接从文件读取 7 个关节角度，不使用 rclpy 订阅
- 这种方式不和 teleop 的 `ros2_control_node` 抢 DDS 资源，100% 无冲突

### CAN 直接解码（替代 ros2_control_node）
当 `ros2_control_node` 的 ArmHardware 激活卡死时，可以用 `can_joint_pub.py` 直接从 CAN 总线获取关节数据。

**MIT 协议解码公式（C 源码 → Python）：**
```python
MIT_POS_MIN, MIT_POS_MAX = -12.57, 12.57
rad = raw / 65535.0 * (MIT_POS_MAX - MIT_POS_MIN) + MIT_POS_MIN
```

**CAN 帧格式（来自 `common/protocol.c`）：**
```
29-bit ID: [frame_type(5)][mode_state(2)][fault_code(6)][motor_id(8)][master_id(8)]
           frame_type = 0x02 (feedback)
           motor_id = 1-7 (L1-L7)
Data[8]:   [pos_hi][pos_lo][vel_hi][vel_lo][torque_hi][torque_lo][temp_hi][temp_lo]
```

- `can_joint_pub.py` 放在 `/home/telecontrol/workspace/can_joint_pub.py`，同步到远程 `/tmp/can_joint_pub.py`

### OOM Killer
- rviz2 在无显示器环境触发 OOM → 连带杀掉 robot_state_publisher
- 必须加 `use_rviz:=false`
- 如果触发，pkill -f "ros2 launch" 全部重启

## 相机采集
- robot_server.py 使用 rclpy CameraCache 后台线程 + compressed topic 订阅
- 一个 background thread 订阅两个 compressed topic，缓存最新 JPEG
- get_observation() 直接从缓存读取，避免每帧 subprocess 开销
- 机械臂关关节动时 rclpy 的 FastDDS 错误会刷屏，不影响功能
- 如果 image_raw/compressed topic 不可用（如启动初期），返回空白图像

## 新增工具

### WebUI 数据采集控制 (`collect_data_web.py`)
位置：容器内 `/opt/workspace/collect_data_web.py`

WebUI 方式替代 CLI 采集，提供 Connect/Start/Stop/Finish 控制。通过 WebSocket 与后台 DataCollector 通信。

**界面布局：**
```
┌────────── 左 (380px) ──────────┬────── 右 (flex:1) ───────────┐
│ ┌─ Connection ───────────────┐ │ ┌─ Robot Monitor ──────────┐ │
│ │ [Host] [Port] [Res] [Cam]  │ │ │ [● connected] fps       │ │
│ │ [Connect] [Disconnect]     │ │ │ ┌─Front──┐ ┌─Wrist──┐  │ │
│ └────────────────────────────┘ │ │ │ camera │ │ camera │  │ │
│ ┌─ Recording ───────────────┐ │ │ └────────┘ └────────┘  │ │
│ │ [Task] [Start/Stop/Finish]│ │ │ Joint bar graphs       │ │
│ │ Status / Save path        │ │ │ Hand State             │ │
│ └────────────────────────────┘ │ └────────────────────────┘ │
│ ┌─ Episodes ────────────────┐ │                              │
│ │ #│Task│Frames│Duration    │ │                              │
│ └────────────────────────────┘ │                              │
└────────────────────────────────┴──────────────────────────────┘
```

右侧 Monitor 通过第二条 WebSocket 直连 robot_server（与采集控制的 WS 独立），每 100ms 轮询 `get_observation`。

**启动方式：**
```bash
# 宿主机一键管理（推荐）
/home/telecontrol/start_collect_web.sh start    # 启动
/home/telecontrol/start_collect_web.sh stop     # 停止
/home/telecontrol/start_collect_web.sh status   # 状态
/home/telecontrol/start_collect_web.sh logs     # 日志

# 或容器内直接启动（默认使用 8081/8082，可通过 --robot-host 指定远程 IP）
docker exec pi /opt/workspace/openpi/.venv/bin/python \
  /opt/workspace/collect_data_web.py --http-port 8081 --ws-port 8082
```

**架构：**
```
宿主机 localhost:8081 → TCP forwarder / iptables → Docker :8081 (HTTP 页面)
宿主机 localhost:8082 → TCP forwarder           → Docker :8082 (采集控制 WS)
浏览器 WS2            → 直接连接                  → 远程 :8765 (robot_server 监控)
```

**WebSocket 协议（WebUI → DataCollector）：**
```json
{"type":"connect", "host":"192.168.127.24", "port":8765}   # 连接机器人
{"type":"disconnect"}                                        # 断开
{"type":"start", "task":"pick up the red cube"}              # 开始 episode
{"type":"stop"}                                               # 停止当前 episode
{"type":"finish"}                                             # 完成采集（计算统计信息）
```

**WebSocket 协议（DataCollector → WebUI）：**
```json
{
  "type": "status",
  "connected": true,
  "recording_state": "idle|warmup|recording",
  "episode_idx": 1,
  "frame_count": 127,
  "elapsed": 12.3,
  "episodes_done": [{"idx":1, "task":"...", "frames":300, "duration":30.0, "path":"..."}],
  "finished": false,
  "dataset_path": "/workspace/data/dataset_xxx",
  "cameras": "dual|front"
}
```

`hardware_prepare.sh` 和 `teleop_prepare.sh` 已废弃（位于回收站），不要使用。

数据采集模式不需要启动 teleop。如需遥操作，参考 `TELEOP_GUIDE.md`。

### 宿主机管理脚本 (`start_collect_web.sh`)

管理 WebUI 服务在容器内的启停 + 宿主机端口转发。

### 全组件管理脚本 (`start_all.sh`)

位置：`/home/telecontrol/workspace/start_all.sh`

替代 `start_collect_web.sh`，统一管理所有服务。

**用法：**

```bash
# 数据采集 WebUI（端口 8081/8082）
bash /home/telecontrol/workspace/start_all.sh data-collection start
bash /home/telecontrol/workspace/start_all.sh data-collection stop

# 推理监测 WebUI（端口 8090）
bash /home/telecontrol/workspace/start_all.sh inference start
bash /home/telecontrol/workspace/start_all.sh inference stop

# 远程机器人服务（SSH 到远程机器启动相机/CAN/手/robot_server）
bash /home/telecontrol/workspace/start_all.sh remote start
bash /home/telecontrol/workspace/start_all.sh remote stop

# 单端口转发管理
bash /home/telecontrol/workspace/start_all.sh forwarder 8090 start
bash /home/telecontrol/workspace/start_all.sh forwarder 8081 stop

# 全局
bash /home/telecontrol/workspace/start_all.sh start      # 启动所有本机服务
bash /home/telecontrol/workspace/start_all.sh stop       # 停止所有本机服务
bash /home/telecontrol/workspace/start_all.sh status     # 查看状态
bash /home/telecontrol/workspace/start_all.sh logs       # 查看日志
```

**原理：**
- 每个服务在容器内以 `nohup` 后台进程运行
- 宿主机 TCP forwarder 自动创建（Python 脚本在 `/tmp/forward_<port>.py`）
- forwarder PID 保存在 `/tmp/forward_<port>.pid`
- 服务 PID 保存在 `/home/telecontrol/workspace/logs/<service>.pid`
- 停止时先杀 forwarder，再杀容器内进程

### 推理监测 WebUI (`inference_webui.py`)

位置：容器内 `/opt/workspace/inference_webui.py`，宿主机端口 8090。

独立推理监测界面，不依赖机器人连接。输入任务 prompt，使用占位图（灰色 224×224）或真实相机帧进行推理，实时显示模型预测的关节角。

**功能：**
- 文本框输入 task prompt
- 点击「推理」触发 `policy.infer()`（后台线程，不阻塞 HTTP）
- 浏览器轮询 `/result` 获取结果
- 显示 7 个关节角预测值（弧度）
- 显示 50 步完整 action plan 表格

**HTTP API：**
| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | HTML 页面 |
| `/events` | GET | SSE 推送模型状态（model_loaded, connected 等） |
| `/infer` | POST | 触发推理，body: `{"prompt":"..."}`，返回 HTTP 202 |
| `/result` | GET | 获取推理结果，`{"status":"ok/inferring/error", "pred_joints":[...], "action_seq":[[...]]}` |

**模型加载：**
- 加载自定义 `.npy` 格式 checkpoint（streaming 保存的 51 个文件，13GB）
- 使用 `Policy` 类封装 transforms 链（InjectImageMask → InjectDefaultPrompt → ResizeImages → TokenizePrompt → PadStatesAndActions → Normalize → model_transforms）
- 输出经过 Unnormalize 反归一化，单位为弧度
- 首推理 JIT 编译约 30s（Thor GPU sm_101 降级），后续推理 ~750ms

**启动方式：**
```bash
# 容器内
/opt/workspace/openpi/.venv/bin/python3 /opt/workspace/inference_webui.py --port 8090

# 宿主机端口转发（容器 IP 可能变化）
python3 /tmp/forward.py <CONTAINER_IP> 8090 8090 &

# 浏览器
http://localhost:8090
```

**关键实现细节：**
- 使用 `ThreadingHTTPServer` 支持多线程并发（SSE + POST + GET 互不阻塞）
- `_INFER_RESULT` 全局变量存储推理结果，使用 `status` 字段区分 ok/inferring/error
- 推理输入使用占位灰图 `np.full((224,224,3), 80, dtype=np.uint8)`，不依赖相机

### WebUI 无相机占位符
当相机不可用时（`has_front_image=false` 或 `has_wrist_image=false`），Monitor 显示灰色 "No camera" 占位符，不会把图像显示到错误的槽位。

### 相机启动（关键顺序）
远程有两个 Orbbec 相机：335L（正面）和 305（夹爪）。**必须先启动 335L（带 serial 过滤锁定 UVC 设备），等 10 秒后再启动 305。** 否则 305 的 launch（无 serial 过滤）会抢占 335L 导致话题映射错误。参考 `fix_cameras.sh`。

---

## 已知 Bug 与修复

### 1. `not self._dataset` 永远为 True（关键 Bug）

**根因：** `LeRobotDataset` 继承 `torch.utils.data.Dataset`。当数据集为空（刚创建，还没加 frame）时，`__len__()` 返回 0。Python 的 `bool` 检查回退到 `__len__`，因此 `bool(empty_dataset) == False`，`not empty_dataset == True`。

**影响：** `_step_record` 中的 `if not self._dataset: return` 会跳过每一帧，导致 frames 永远为 0。

**修复：** 用 `self._dataset is None` 替代 `not self._dataset`。所有地方都要用 `is None` 判断，包括 `self._robot`。

### 2. `save_episode()` 视频编码阻塞主循环

**根因：** `LeRobotDataset.save_episode()` 触发 SVT-AV1 视频编码（640x480 双路）。编码 20 帧约需 10 秒，期间整个 `_run_loop` 被阻塞，无法处理 stop 命令。

**修复：** `save_episode()` 在后台线程执行，stop 指令立即设置 `_state = "idle"` 停止新帧录制。

### 3. `recv()` 无超时导致永久阻塞

**根因：** `websockets.sync` 的 `recv()` 默认无超时参数。当网络异常或 robot_server 无响应时，`_request_observation` 永久挂起。

**修复：** 在 `robot_client.py` 中给每个 `recv()` 添加 `timeout` 参数：
```python
# _request_observation
meta = json.loads(self._ws.recv(timeout=10))    # 元数据 10s
jpeg_data = self._ws.recv(timeout=5)             # JPEG 5s
# send_action
result = json.loads(self._ws.recv(timeout=10))   # action 结果 10s
```

### 5. `LeRobotDataset.__init__` 中 `torch.stack(hf_dataset["timestamp"])` 报错

**根因：** 新版 HuggingFace `datasets` 库中，`dataset["column"]` 返回 `Column` 对象而非 tensor 列表。`torch.stack` 无法处理。

**修复：** 将 `.venv/lib/python3.11/site-packages/lerobot/common/datasets/lerobot_dataset.py` 中的两处 `torch.stack(...)` 改为：
```python
torch.stack([torch.as_tensor(t) for t in self.hf_dataset["timestamp"]])
torch.stack([torch.as_tensor(e) for e in self.hf_dataset["episode_index"]])
```

### 6. `delta_timestamps` 参数触发同一 bug + action chunk 替代方案

**根因：** `create_torch_dataset` 中 `LeRobotDataset(repo_id, delta_timestamps=...)` 触发上述 bug。

**修复：** 在 `data_loader.py` 中新增 `ActionChunkDataset` wrapper 替代 `delta_timestamps`：
```python
class ActionChunkDataset(Dataset):
    """Wrap base LeRobotDataset, build action chunks of length action_horizon
    by fetching subsequent frames. Repeats last frame for sequences extending
    beyond dataset boundary (padding)."""
```

同时在 `create_torch_dataset` 中自动检测数据集的实际 action key 名（"action" 或 "actions"）。

### 7. GPU 训练 bf16→f16 LLVM 崩溃（Thor CC 11.0）

**根因：** Thor GPU（CC 11.0）的 LLVM 后端不支持 bf16→f16 的精度转换。JIT 编译 `jax.random.key()` 或训练 step 时崩溃。

**报错：**
```
Unsupported conversion from bf16 to f16
LLVM ERROR: Unsupported rounding mode for conversion.
```

**修复：** `scripts/train.py` 中的 `jnp.bfloat16` 改为从 `config.model.dtype` 读取：
```python
# 改前
params = nnx_utils.state_map(params, config.freeze_filter,
    lambda p: p.replace(p.value.astype(jnp.bfloat16)))
# 改后
params = nnx_utils.state_map(params, config.freeze_filter,
    lambda p: p.replace(p.value.astype(getattr(jnp, config.model.dtype))))
```
训练时用 `--model.dtype=float32` 避免崩溃。

### 8. `jax[cuda13]` 安装失败 / Thor GPU ptxas 版本过旧

**根因：** JAX 0.5.3 依赖的 `nvidia-cuda-nvcc-cu12` 包的 ptxas 不支持 sm_110（Thor CC 11.0）。`jax[cuda13]` 需要同时升级 JAX≥0.7.0，但需要 numpy≥2.0，与 openpi 的 numpy<2.0 冲突。

**修复：** 独立安装 `nvidia-cuda-nvcc==13.3.33` 并替换 ptxas：
```bash
uv pip install nvidia-cuda-nvcc
cd .venv/lib/python3.11/site-packages/nvidia
mv cuda_nvcc/bin/ptxas cuda_nvcc/bin/ptxas.old
ln -s ../cu13/bin/ptxas cuda_nvcc/bin/ptxas
```
新 ptxas 支持 sm_110，JAX 可以在 GPU 上运行（降级 sm_101）。警告 "Unknown compute capability 11.0" 可忽略。

### 9. WebUI 摄像头模式（Dual / Front Only）

`collect_data_web.py` 中增加 `Cam` 下拉框，支持两种模式：

| 模式 | 录制的特征 |
|------|-----------|
| Dual | `observation.images.front` + `observation.images.wrist` |
| Front Only | 仅 `observation.images.front`（wrist 被完全移除） |

Front Only 模式下：
- 数据集创建时不含 `observation.images.wrist` 特征
- `_step_record` 跳过 wrist 数据写入
- 不生成 wrist 视频文件，节省编码时间和存储空间

### 10. 遥操作与数据采集的控制器冲突

**问题：** `teleop_demo.launch.py` 和 `demo.launch.py` 都会拉起自己的 `ros2_control_node`，导致两个 controller_manager 抢占同一套 CAN 硬件接口。具体表现：

| 场景 | 启动的 launch | 后果 |
|------|-------------|------|
| 遥操作中启动采集 | `demo.launch.py` | 第二个 ros2_control_node 用不带 `left_arm_direct_controller` 的 YAML，覆盖掉遥操作的 direct controller |
| 采集完成后切遥操作 | `teleop_demo.launch.py` | spawner 报告 "Resource conflict: L1_joint/position is already claimed" |

**控制器状态查看：**
```bash
ros2 control list_controllers
ros2 control set_controller_state left_arm_controller inactive
ros2 control set_controller_state left_arm_direct_controller active
```

**FastDDS 共享内存冲突：** 旧进程残留的 `/dev/shm/fastrtps_*` 锁文件会导致新 spawner 卡在 "waiting for service /controller_manager/list_controllers"。清理方式：
```bash
rm -f /dev/shm/fastrtps_*
```

### 11. ros2_control_node ArmHardware 激活死锁

**问题：** `ros2_control_node` 的 `on_activate()` 获取互斥锁后等待 CAN 应答，但 CAN 接收回调需要同一把锁 → 死锁。每次 CAN 接口被重置（modprobe -r gs_usb、ip link set can0 down/up）后都会触发。

**表现：** 23 个线程全睡在 `futex_wait_queue`，controller_manager 服务不响应，`ros2 control list_controllers` 超时。

**修复：**
- 临时方案：用 `can_joint_pub.py` 从 CAN 直接解码关节数据，绕过 ros2_control_node
- 根治方案：arm 断电重开 → 干净启动（不要先重置 CAN）

### 12. robot_server.py 文件损坏后 WS 不接受连接

**问题：** 编辑 `robot_server.py` 后服务器启动但不接受 WebSocket 连接。

**根因：** 文件被 scp 时损坏（空文件、DOS 换行符等）。

**修复：** 和 bak2 对比：
```bash
diff /home/sunrise/robot_server.py /home/sunrise/robot_server.py.bak2
md5sum /home/sunrise/robot_server.py /home/sunrise/robot_server.py.bak2
```
bak2 是无修改的原始工作版本。

### 13. robot_server 的 rclpy 和 teleop 冲突

**问题：** robot_server 的 CameraCache 使用 rclpy 订阅 `/joint_states`，和 teleop 的 `ros2_control_node` 抢 DDS 资源，导致双方数据都停更。

**修复：** 使用 v2 版 `robot_server.py`（从文件 `/tmp/joint_positions.json` 读关节数据，不做 rclpy 订阅）。关节数据由 `can_joint_pub.py`（无 rclpy）从 CAN 总线直接解码写入。

### 14. grasp_bringup.srv 导入失败

**问题：** `hand_grasp_server.py` 导入 `from grasp_bringup.srv import ExecuteHandGrasp` 时报 `UnsupportedTypeSupport: Could not import 'rosidl_typesupport_c'`。

**根因：** `grasp_bringup` 的 `.so` 库有未定义符号 `grasp_bringup__srv__set_teach_mode__response__convert_to_py`，编译时引入的 `SetTeachMode` 服务未正确生成类型支持。

**修复：** 使用 `hand_state_pub.py` 替代（直接 SDK 读取 + pub，不依赖 grasp_bringup）。

### 13. 数据采集 WebUI 集成 Robot Monitor

`collect_data_web.py` 中内嵌了 `web_monitor.py` 的监控面板，通过**第二条 WebSocket** 直连 `robot_server`（端口 8765），与采集控制的 WS 独立运行。

**通信架构：**
```
浏览器
  ├── WS1 → localhost:8082 → collect_data_web DataCollector (控制: Connect/Start/Stop/Finish)
  └── WS2 → robot_host:8765 → robot_server (监控: get_observation, 100ms 轮询)
```

**Monitor 正常工作需要以下条件全部满足：**
| 条件 | 检查方法 |
|------|---------|
| `robot_server` 在远程机器运行 | `ss -tlnp \| grep 8765` |
| `ros2_control_node` 或 `can_joint_pub.py` 运行 | `ps aux \| grep -E "ros2_control_node\|can_joint"` |
| 相机驱动运行 (335L + 305) | `ros2 topic list \| grep camera` |
| 关节数据发布 | `cat /tmp/joint_positions.json` (can_joint_pub) 或 `ros2 topic info /joint_states` |

如果硬件栈未启动，Monitor 会显示 "waiting for data..."（因为 `robot_server` 返回的 `joint_positions` 和 `hand_state` 为 null），这不是 bug。

**已知修复：** `renderMonJoints()` 和 `renderMonHand()` 添加了 null/empty 保护，无数据时不崩溃。

### 14. `teleop_step()` 不支持 `cameras` 参数导致 Start 卡 idle

**根因：** `collect_data_web.py` 的 `_step_warmup` 和 `_step_record` 调用 `self._robot.teleop_step(cameras=self._cameras)`，但原始 `robot_client.py` 的 `teleop_step(self, record_data=False)` 不接受 `cameras` 关键字参数。

`TypeError` 被 `except Exception` 捕获后，`print(f"Warmup error: {e}")` 因 stdout 重定向到文件使用**全缓冲**而不可见，表现为 Start 按钮无响应、状态卡在 idle。

**修复：**
1. 移除 `teleop_step` 调用中的 `cameras` 参数（相机模式仅在数据集创建和帧写入时生效）
2. 所有 error print 添加 `flush=True`，确保日志立即刷新

---

| 操作 | 耗时 | 说明 |
|------|------|------|
| `_request_observation`（首次） | ~3.4s | 含 WebSocket 握手 + 图片传输 |
| `_request_observation`（稳定后，640×480） | 0.3-0.7s | 双路 JPEG (640x480) 网络传输 |
| `_request_observation`（稳定后，320×240） | 0.03-0.04s | 单路 320x240，~10x 加速 |
| `_request_observation`（稳定后，160×120） | 0.02-0.03s | |
| `can_joint_pub.py` 解码帧率 | ~100Hz | 直接从 can0 读 MIT 帧，无 ROS2 开销 |
| `LeRobotDataset.create()` | 5-15s | 创建数据集目录 + 初始化元数据 |
| warmup 30帧 (640×480) | 15-20s | 每帧 0.5s × 30 |
| warmup 30帧 (320×240) | 1-2s | 每帧 0.03-0.04s × 30 |
| `save_episode()` (10 帧) | ~5s | AV1 编码 + parquet 写入 |
| `save_episode()` (30 帧) | ~15s | 帧数线性增长 |
| 有效采集帧率 (640×480) | 1.5-2 fps | 受限于 robot_server 的 JPEG 传输 |
| 有效采集帧率 (320×240) | ~20-30 fps | 大幅提升 |
| GPU 训练单步 (CPU 降级) | ~20s/step | JAX CPU 模式，JIT 编译慢 |
| GPU 训练单步 (GPU float32) | ~2.7s/step | Thor GPU，sm_101 降级模式 |
| 模型加载（推理 WebUI） | ~50s | 加载 13GB checkpoint + JIT 首次编译 |
| 推理（首步，含 JIT） | ~30s | `sample_actions` JIT 编译 |
| 推理（后续） | ~750ms | 50 步 diffusion 采样 |

## 训练

### 自定义训练配置 (`pi05_arm_dataset`)
配置文件：`src/openpi/training/config.py`，添加到 `_CONFIGS` 列表。

```python
TrainConfig(
    name="pi05_arm_dataset",
    model=pi0_config.Pi0Config(pi05=True, dtype="float32"),
    data=SimpleDataConfig(repo_id="/workspace/data/dataset_<timestamp>", ...),
    num_train_steps=200, log_interval=10,
    batch_size=12,
    model.dtype=float32,
)
```

### 新增 transforms（`transforms.py`）
| transform | 用途 |
|-----------|------|
| `ConvertImageChwToHwc()` | LeRobot CHW → HWC，float 转 uint8 |
| `InjectImageMask()` | 为缺失相机补零 + 生成 image_mask |

### LeRobot 补丁
`lerobot_dataset.py` 中三处 `torch.stack(Column)` → `torch.stack([torch.as_tensor(t) for t in ...])`

### Checkpoint 保存（streaming 避免 OOM）
orbax 的 `CheckpointManager.save()` 一次性传输 12.5GiB 导致系统卡死/OOM。
改为逐个数组流式保存 `.npy` 文件（`scripts/train.py` 末尾的自定义代码）：

```
for key, val in flatten_dict(train_state.params.to_pure_dict()).items():
    cpu_val = np.asarray(val)
    np.save(ckpt_path / f"{key_str}.npy", cpu_val)
    del val, cpu_val; gc.collect()
```

### Docker 内存限制
容器默认 cgroup 限制可能仅 10.8GiB，checkpoint 保存时 OOM。如遇 exit 137：
```bash
docker update --memory="64g" --memory-swap="64g" pi
```

### 训练输出格式
```
推理输入: images{base_0_rgb, left_wrist_0_rgb, right_wrist_0_rgb} + state(32)
推理输出: actions[50, 32] (normalized float32, ±3σ)
          actions[:, :8] = [L1..L7, gripper] (归一化)
          actions[:, 8:] = 0 (padding)

Denormalize: real_value = normalized * std + mean
```

### 训练日志中打印 loss
由于 nnx.Module 的 `__getattr__` 限制，直接调用 `model.compute_loss()` JIT 编译时会报 `TracerArrayConversionError`。推荐使用 `serve_policy.py` 部署推理，或自行构建完整观测输入。

## SSH
```bash
export ROBOT_HOST=192.168.127.24
sshpass -p 'sunrise' ssh -o StrictHostKeyChecking=no "sunrise@\$ROBOT_HOST"
sshpass -p 'sunrise' scp -o StrictHostKeyChecking=no <local> "sunrise@\$ROBOT_HOST":<remote>
```

## 常见问题排查
1. **L1 关节初始化失败** → can1 没配或 calibration_ws 没 source
2. **OOM killer** → rviz2 没加 use_rviz:=false
3. **topic 没数据** → 检查 USB 连接 `lsusb | grep orbbec`
4. **send_action 超时** → 机械臂忙或轨迹规划失败，~20s 阈值
5. **robot_server 崩溃** → 检查 8765 端口占用，看 stdout
6. **内存泄漏** → 别用 rclpy 长连接订阅
7. **没有 /dev/video*** → 重新插拔 USB，或重启 camera driver
8. **CAN send buffer overflow** → 增大 CAN txqueuelen 和 socket buffer：`sudo ip link set can0 txqueuelen 1000`；重启前清理 `/dev/shm/fastrtps_*`
9. **Spawner 一直 waiting for service** → 旧 DDS 锁文件冲突：`rm -f /dev/shm/fastrtps_*` 然后重启 launch
10. **两个控制器争抢 position 接口** → 同时只能有一个 active：`ros2 control set_controller_state left_arm_controller inactive && ros2 control set_controller_state left_arm_direct_controller active`
11. **训练崩溃：bf16→f16 LLVM error** → Thor GPU 不支持 bf16，加 `--model.dtype=float32`
12. **`ros2_control_node` 卡死在 ArmHardware 激活** → 用 `can_joint_pub.py` 从 CAN 直接解码关节数据。修复死锁需要 arm 断电重开 + 干净启动 teleop。
13. **robot_server 修改后不接受 WS 连接** → 检查文件是否损坏：`diff robot_server.py robot_server.py.bak2`
14. **robot_server 的 rclpy 和 teleop 冲突** → 用 v2 版（从文件读关节数据）替代 rclpy 订阅。
15. **grasp_bringup.srv 导入失败** → 用 `hand_state_pub.py` 替代（SDK 直读，不依赖 grasp_bringup）。
16. **JAX random.key 崩溃：ptxas too old** → 升级 nvidia-cuda-nvcc 到 13.x 版本。

---

## 下一步目标

### 1. 推理结果 3D 可视化（建议优先）

将模型预测的 7 个关节弧度值在 WebUI 中以 3D 机械臂形式展示。

**可选方案：**

| 方案 | 实现方式 | 依赖 | 复杂度 |
|------|---------|------|--------|
| **A. three.js 内嵌 WebUI** | 在现有 `inference_webui.py` 的 HTML 中加载 three.js CDN，用 `pred_joints` 驱动 7 连杆铰接臂模型 | 无（浏览器端渲染） | 中 |
| **B. RViz + ROS2** | 写一个 ROS2 节点订阅预测值，发布到 `/joint_states`，加载机械臂 URDF 显示 | 远程 ROS2 环境 + URDF | 低（但依赖远程） |
| **C. Meshcat** | 起 meshcat-server，推关节角数据，浏览器打开 meshcat 页面 | meshcat | 低 |
| **D. Open3D / matplotlib** | 服务器端渲染 3D 图，推图片到 WebUI | open3d / matplotlib | 低（但无交互） |

**推荐方案 A**：直接集成到推理 WebUI，不依赖 ROS2，浏览器即可查看。预测值与推理结果在同一页面实时联动。

### 2. 模型部署到真实机器人

- 使用 `serve_policy.py`（或 `serve_policy_float32.py`）启动推理服务
- 将预测的 `actions[:, :8]` 通过 robot_server 的 `send_action` 发送到机械臂
- 需要解决：推理频率与执行频率匹配、安全性检查、急停机制

### 3. 更多训练数据

- 采集更多样化的数据集（不同物体、位置、光照）
- 增加训练步数（1000+）
- 从 pi05_base 预训练权重微调（当前是从随机初始化训练）

### 4. 相机输入支持

- 推理 WebUI 当前使用占位灰图
- 接入远程相机帧后，模型可基于视觉输入推理
- 需要 WebSocket 连接 robot_server 获取实时相机帧
