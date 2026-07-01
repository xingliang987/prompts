# 数据采集流程指南

## 远程 IP 配置

设置环境变量 `ROBOT_HOST` 指定远程机器 IP：
```bash
export ROBOT_HOST=192.168.127.24
```
代码和脚本中默认使用此变量，无需在每个命令中手动指定 IP。

## 系统架构

```
本机 (spark-adaf, Docker pi_dev)
  └── robot_client.py ──WebSocket──→ 远程 (ROBOT_HOST:8765)
                                       ├── robot_server.py (WebSocket 桥接)
                                       ├── can_joint_pub.py (CAN→关节数据, 无 rclpy)
                                       │    └── can0 (MIT 协议解码)
                                       ├── hand_state_pub.py (SDK→灵巧手状态)
                                       ├── Gemini 335L (正前方, /camera)
                                       ├── Gemini 305 (夹爪, /camera_wrist)
                                       └── [teleop] launch_teleop.sh → ros2_control_node
```

**关节数据无需 `ros2_control_node`** — `can_joint_pub.py` 直接从 CAN 总线解码 MIT 协议反馈帧，不创建 rclpy 节点，不和 teleop 抢 DDS 资源。

---

## 启动流程（按顺序）

### 远程机器 ROBOT_HOST

**0. 相机 USB**
```bash
# 确认两台 Orbbec 相机都被 USB 检测到
lsusb | grep -i orbbec
# 应该看到:
#   Bus 002 Device ...: ID 2bc5:0804 Orbbec Gemini 335L   (正面)
#   Bus 001 Device ...: ID 2bc5:0840 Orbbec Gemini 305     (夹爪)
```
- 相机需要在启动驱动**之前**插好 USB
- 335L 接 USB3.0 口（Bus 002），305 接 USB2.0 口（Bus 001）
- 如果没检测到，检查物理连接

**1. 启动遥操作 ROS 环境（一键）**

在远程机器上执行：
```bash
bash /home/sunrise/Desktop/testing/teleop_launch_scripts/terminal1.sh
```
该脚本自动完成：
- CAN 总线初始化 (can0 + can1, txqueuelen 1000)
- 启动 `teleop_demo.launch.py`（含 robot_state_publisher + ros2_control_node + joint_state_broadcaster + left_arm_direct_controller）
- 等待约 30-40 秒关节进入 MIT mode

**不需要**再手动初始化 CAN 或启动其他 ROS 服务。

**2. 确认关节数据**
```bash
source /opt/ros/humble/setup.bash
source /home/sunrise/ros2_ws/install/setup.bash
ros2 topic echo /joint_states --once --field position
```

**3. WebSocket 桥接服务**

```bash
source /opt/ros/humble/setup.bash
source /home/sunrise/ros2_ws/install/setup.bash
source /home/sunrise/calibration_ws/install/setup.bash

python3 /home/sunrise/robot_server.py --port 8765
```

**3b. CAN 关节解码器（可选，当 ros2_control_node 卡死时替代）**

如果 `ros2_control_node` 的 ArmHardware 激活卡死（`list_controllers` 无响应），可以用 CAN 直接解码获取关节数据：

```bash
python3 /tmp/can_joint_pub.py
```

这个脚本从 `can0` 读取 MIT 协议反馈帧，解码 7 个关节角度，写入 `/tmp/joint_positions.json`。
`robot_server.py` 从该文件读取，完全绕过 `ros2_control_node`，不和 teleop 抢任何资源。

### 本机 Docker (pi_dev)

**5. 验证连接**
```bash
source /workspace/openpi/openpi/bin/activate
PYTHONPATH=/workspace:$PYTHONPATH python3 -c "
from robot_client import NetworkRobot
robot = NetworkRobot('ROBOT_HOST', 8765)
robot.connect()
obs = robot.capture_observation()
print('关节:', obs['observation.state'])
print('图像:', obs['observation.images.front'].shape)
robot.disconnect()
"
```

**6. 数据采集**
```bash
source /workspace/openpi/openpi/bin/activate
python3 /workspace/collect_data.py \
  --host ROBOT_HOST --port 8765 \
  --episodes 50 --episode-time 30 \
  --fps 10 --task "pick up the red cube"
```

---

## 文件清单

### 本机 /home/arm/

| 文件 | 作用 |
|------|------|
| `robot_client.py` | LeRobot Robot 网络 wrapper，实现 `teleop_step()` / `capture_observation()` / `send_action()` |
| `collect_data.py` | 数据采集脚本（CLI, 旧式） |
| `collect_data_web.py` | **WebUI 数据采集控制（推荐）** |
| `robot_server.py` | 已同步到远程 `/home/sunrise/robot_server.py` |
| `web_monitor.py` | Web 监控界面（已集成到 WebUI 中） |
| `start_collect_web.sh` | 宿主机一键管理脚本（启停 + 端口转发） |

### 远程 ROBOT_HOST

| 文件 | 作用 |
|------|------|
| `/home/sunrise/robot_server.py` | WebSocket + ROS2 CLI 桥接服务（v2: 从文件读关节数据） |
| `/tmp/can_joint_pub.py` | CAN 总线→关节数据解码器（不创建 rclpy 节点） |
| `/tmp/hand_state_pub.py` | LinkerHand SDK → 灵巧手状态 |
| `/home/sunrise/ros2_ws/` | ROS2 工作空间（grasp_bringup, arm_moveit, arm_hardware） |
| `/home/sunrise/calibration_ws/` | 标定参数工作空间 |
| `/home/sunrise/vision_ws/` | Orbbec 相机驱动（gemini_330_series.launch.py） |
| `/home/sunrise/Desktop/testing/launch_teleop.sh` | 遥操作启动脚本（含 CAN 配置 + teleop_demo.launch） |
| `/home/sunrise/Desktop/testing/teleop_launch_scripts/terminal1.sh` | 一键启动入口（调用 launch_teleop.sh） |

### 相机启动（关键顺序）

远程机器有两个 Orbbec 相机：335L（正面）和 305（夹爪）。**必须按顺序启动**，否则 305 的 launch 会抢走 335L：

```bash
# 1. 先启动 335L（带 serial 过滤，锁定 UVC 设备到 /camera 话题）
ros2 launch orbbec_camera gemini_330_series.launch.py \
  camera_name:=camera serial_number:=CP2G853000G1 \
  enable_point_cloud:=false enable_depth:=true \
  depth_width:=640 depth_height:=480 color_width:=640 color_height:=480 \
  color_fps:=10 depth_fps:=10

# 2. 等 10 秒后，再启动 305（335L 已被占用，只拿到真正的 305）
ros2 launch orbbec_camera gemini305.launch.py \
  camera_name:=camera_wrist \
  enable_point_cloud:=false enable_depth:=false \
  color_width:=640 color_height:=480 color_fps:=10
```

也可以使用一键脚本：
```bash
bash /home/telecontrol/workspace/fix_cameras.sh
```

### 相机规格

| 参数 | 正面 Gemini 335L | 夹爪 Gemini 305 |
|------|------------------|-----------------|
| USB | 3.2 SuperSpeed | 2.1 |
| 串号 | CP2G853000G1 | — |
| 固件 | 1.4.60 / SDK 2.7.6 | — |
| 彩色 | 640x480 @ 10fps, MJPG, rgb8 | 640x480 @ 10fps, MJPG |
| 深度 | 640x480 @ 10fps, Y16 | 不支持 |
| ROS2 Namespace | `/camera` | `/camera_wrist` |
| 关键 Topic | `/camera/color/image_raw/compressed` | `/camera_wrist/color/image_raw/compressed` |

---

## 注意事项

### OOM Killer
- rviz2 在无显示器环境下会占用大量内存并触发 OOM killer，连带杀掉 `robot_state_publisher` 和其他节点
- 启动时必须加 `use_rviz:=false`
- 如果已经触发 OOM，需要 `pkill -f "ros2 launch"` 全部杀掉后重新启动

### FastDDS 序列化错误
- 终端会不断刷 `Fast CDR exception deserializing message` 的错误
- 这是 FastDDS 在多接口/多进程环境下的已知问题，不影响 ROS2 通讯功能

### 关节数据 & gripper 状态
- `joint_state_broadcaster` 发布所有 14 个关节（L1-L7 + R1-R7）
- `robot_client.py` 只取前 7 个（L1_joint ~ L7_joint），加 1 个 gripper 状态
- 关节位置为弧度值
- **observation.state 维度 = 8**（7 关节 + gripper），**action 维度 = 8**（7 关节 + gripper）
- 灵巧手状态通过 `hand_state_pub.py` 以 20Hz 发布到 `/hand_state` topic
- `robot_server.py` 的 CameraCache 订阅 `/hand_state`，在 observation metadata 中返回 `hand_state` 数组

### CAN 直接解码关节数据（绕过 ros2_control_node）
当 `ros2_control_node` 死锁时（ArmHardware 激活卡死），可以用 `can_joint_pub.py` 直接从 CAN 总线解码关节角度：

```
can0 ─→ can_joint_pub.py ─→ /tmp/joint_positions.json ─→ robot_server.py ─→ WebUI
```

**原理**：arm 的关节电机以 200Hz 在 can0 上发送 MIT 协议反馈帧，每帧 8 字节包含位置/速度/力矩/温度编码值。

**CAN 帧格式（29-bit ID, 8 字节数据）：**
```
位 24..28: frame_type (0x02 = 反馈帧)
位 22..23: mode_state
位 16..21: fault_code
位 8..15:  motor_id (1-7 = L1-L7)
位 0..7:   master_id

数据字节:
  [0-1]: position_raw (uint16, 大端)
  [2-3]: velocity_raw (uint16, 大端)
  [4-5]: torque_raw   (uint16, 大端)
  [6-7]: temperature  (uint16, 大端, 单位 0.1°C)
```

**解码公式：**
```python
# uint16 → 弧度
MIT_POS_MIN = -12.57
MIT_POS_MAX = 12.57
rad = raw / 65535.0 * (MIT_POS_MAX - MIT_POS_MIN) + MIT_POS_MIN
```

**文件**：`/home/telecontrol/workspace/can_joint_pub.py`（同步到远程 `/tmp/can_joint_pub.py`）

### LinkerHand 灵巧手
- 灵巧手为 **二值控制**，只有全开 / 全关两个状态
  - `finger_move(pose=[0] * 6)` → 握拳（闭合）
  - `finger_move(pose=[255] * 6)` → 全开
  - 6 个手指参数中只有第一个有效，其余 5 个未使用
- 无中间位置反馈，`get_state()` 返回 `[20, 0, 0, 0, 0, 0]` 这样的 6 维数组（0~255），首值为当前手指位置
- gripper 阈值映射（`robot_server.py` / `robot_client.py` 一致）：
  - **0.0** → 张开
  - **> 0.0** → 闭合
  - 无死区（灵巧手只有开关，没有保持逻辑）
- 状态追踪方式：client 端根据上次发送的 command 记录 `_gripper_state`，无硬件反馈闭环

### ROS2 服务
| 服务 | 类型 | 用途 | 请求字段 | 注 |
|------|------|------|---------|----|
| `/execute_hand_grasp` | `ExecuteHandGrasp.srv` | 灵巧手控制 | `grasp_type` (open/close/grasp), `arm_side` | 非 `command` 字段 |
| `/execute_motion_step` | `ExecuteMotionStep.srv` | 关节动作 | `step_type`, `arm_side`, `joint_positions[7]`, ... | 超时阈值 ~20s |
| `/stop_motion` | `StopMotion.srv` | 紧急停止 | 无 | |

### 采集脚本
- 当前 `teleop_step()` 的 action 为占位值（复制了当前关节状态）
- 实际采集时需要接入 VR 数据替换 `dummy_action`
- 每帧调用 `teleop_step(record_data=True)`，不感知时序
- 一个 episode 是一条完整演示（~30 秒 / 300 帧 @ 10fps）

### 多 task 数据集管理
- **一次采集 = 一个数据集**，每个数据集只含一个 task（所有 episodes 共用同一个 `--task`）
- 换 task 就改 `--task` 重新跑一次，输出到不同目录：

  ```bash
  python3 /workspace/collect_data.py --task "pick up the red cube"  --episodes 50 --output data/pick_red_cube
  python3 /workspace/collect_data.py --task "place on tray"         --episodes 50 --output data/place_on_tray
  python3 /workspace/collect_data.py --task "push the button"       --episodes 50 --output data/push_button
  ```

- 训练时多个数据集组合加载，框架自动处理采样平衡：

  ```python
  from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

  datasets = [
      LeRobotDataset("data/pick_red_cube", root="."),
      LeRobotDataset("data/place_on_tray", root="."),
      LeRobotDataset("data/push_button", root="."),
  ]
  ```

- 每个 frame 的 `task` 字段告诉模型当前该执行什么指令，所以不同 task 之间不能用同一个 prompt

### 服务调用超时
- `send_action()` 调用 `/execute_motion_step` 服务，可能超时（~20 秒阈值）
- 机械臂忙或轨迹规划失败时会返回错误
- 夹爪服务字段为 `command`，已在 server 端处理

### 相机
- 335L 初始化约 2 秒，305 约 3 秒
- 使用 compressed topic 获取 JPEG（`/camera/.../image_raw/compressed`）
- 如果 image_raw 不出数据，先 `lsusb | grep orbbec` 确认 USB 检测到设备
- 彩色帧率 10fps，和采集帧率一致（`--fps 10`）
- 夹爪相机 305 不支持深度，`enable_depth:=false`

### 双相机串号冲突
- 两台 Orbbec 同时接在同一 USB hub 时，不指定 serial_number 会拿错设备
- 335L 必须加 `serial_number:=CP2G853000G1`，305 不需要

### Web 监控界面
- `python3 /home/arm/web_monitor.py --robot-host ROBOT_HOST --web-port 8080`
- 浏览器打开 `http://localhost:8080` 即可查看关节角度和相机实时串流
- 浏览器通过 WebSocket 直连 robot_server，独立运行不依赖 Docker
- 关节数据通过 rclpy 后台缓存实时读取，无额外延迟

### WebUI 数据采集控制（推荐）
WebUI 替代 CLI 采集，通过浏览器控制完整的采集流程，实时监控关节和相机画面。

```bash
# 启动 WebUI（宿主机一键管理）
/home/telecontrol/start_collect_web.sh start

# 停止
/home/telecontrol/start_collect_web.sh stop

# 查看状态
/home/telecontrol/start_collect_web.sh status
```

浏览器打开 `http://localhost:8081`，操作步骤：
1. **Connect** — 连接远程机械臂 (ws://192.168.127.24:8765)
2. 输入任务描述
3. **Start** — 开始录制（3s 预热 → 自动录制）
4. **Stop** — 停止当前 episode（后台自动编码保存）
5. 重复 3-4 录制多个 episodes
6. **Finish** — 断开机器人，完成采集

**界面布局：**
```
┌─ 左 (控制) ────────────┬─ 右 (监控) ───────────────┐
│ [Host] [Port] [Res]    │ [● connected] 10 fps       │
│ [Connect] [Disconnect] │ ┌──Front──┐ ┌──Wrist──┐   │
│ [Task] [Start/Stop]    │ │ camera  │ │ camera  │   │
│ Episodes 表格          │ └─────────┘ └─────────┘   │
│                        │ L1  0.207 ████████         │
│                        │ L2  0.001 ░░░░░░░░         │
│                        │ Hand: [255,0,...]          │
└────────────────────────┴────────────────────────────┘
```

右侧 Monitor 直连 robot_server，每 100ms 刷新关节数据和相机画面，无需手动刷新。

**注意：**
- Stop 后状态会显示 "recording" 一段时间，这是正常的——后台在编码 AV1 视频（10 帧约 5s）
- Start 后需要等 5-15 秒数据集创建，然后 3 秒预热，才进入录制
- 分辨率默认 320×240，可在连接面板的 "Res" 下拉框调整
- 摄像头模式默认 Dual（front + wrist），可选 Front Only

### 启动顺序总结
```
1. 远程: bash teleop_launch_scripts/terminal1.sh (CAN + ROS 控制 + 相机)
       ↓
2. 远程: python3 robot_server.py (WebSocket 桥接)
       ↓
3. 本机: http://localhost:8081 (WebUI 采集控制)
```

### 一键启动（数据采集模式）
一键启动所有采集所需服务（相机 + CAN 解码 + 灵巧手 + 桥接）：

```bash
# 本机执行（自动 SSH 到远程）
bash /home/telecontrol/workspace/start_data_collection.sh
```

或者分步执行：
```bash
# 1. CAN 已就绪时跳过 CAN 配置
# 2. 启动相机（参考上面相机启动顺序）
# 3. 启动 CAN 关节解码器
python3 /tmp/can_joint_pub.py
# 4. 启动灵巧手 SDK
python3 /tmp/hand_state_pub.py
# 5. 启动 WebSocket 桥接
python3 /home/sunrise/robot_server.py --port 8765
# 6. 本机打开 http://localhost:8081
```
