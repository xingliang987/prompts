# WORK.md — 机器人数据采集 & pi0.5 VLA 全链路工作报告

## 项目概述

构建一条完整的 pi0.5 VLA 数据采集 → 模型微调 pipeline。
7-DoF 左臂 + LinkerHand 夹爪，通过 WebSocket 桥接 ROS2 Humble 远程控制机器，
Orbbec 双目相机（正面 335L + 夹爪 305），NVIDIA Thor GPU 训练。

---

## 硬件拓扑

```
本机 (原 spark-adaf, 已迁移至新机器)
  └── Docker 容器 (pi)
       ├── collect_data_web.py  (WebUI 服务器 :8081)
       └── openpi (.venv, pi0.5 训练框架)

远程机器 (sunrise@192.168.127.24 → 192.168.31.11)
  ├── robot_server.py          (WebSocket 桥接 :8765)
  ├── can_joint_pub.py         (CAN→关节数据, 无 rclpy)
  ├── hand_state_pub.py        (LinkerHand SDK→手部状态)
  ├── camera_writer.py         (相机→JPEG 文件, 独立 rclpy 进程)
  ├── ros2_control_node        (遥操作控制, 可选启动)
  ├── Gemini 335L (正面, /camera, USB3)
  └── Gemini 305 (夹爪, /camera_wrist, USB2, 已拔除)
```

**IP 变更历史**：`192.168.127.24` → `192.168.31.11`（远程机器网络重配）

---

## 数据链路

### 关节角度
```
can0 (MIT 协议) → can_joint_pub.py → /tmp/joint_positions.json → robot_server → WebUI
```

- 直接从 CAN 总线解码 MIT 协议反馈帧，不创建 rclpy 节点
- 不依赖 `ros2_control_node` / `joint_state_broadcaster`
- 解码公式（来自 `arm_hardware/common/protocol.c`）：
  ```python
  MIT_POS_MIN, MIT_POS_MAX = -12.57, 12.57
  rad = raw / 65535.0 * (MIT_POS_MAX - MIT_POS_MIN) + MIT_POS_MIN
  ```
- CAN 帧格式：29-bit ID `[frame_type(5)][mode_state(2)][fault_code(6)][motor_id(8)][master_id(8)]`
- motor_id 1-7 对应 L1-L7 关节

### 灵巧手
```
LinkerHand SDK (can0) → hand_state_pub.py → /hand_state topic → robot_server → WebUI
```

- SDK 通过 `LinkerHandApi(hand_joint="O6", hand_type="left", can="can0")` 通信
- `get_state()` 返回 6 维数组 (0~255)，`hand_state[0]/255` 作为 gripper 值
- 二值控制：0.0 = 张开, >0.0 = 闭合

### 相机
```
335L USB → orbbec_camera → /camera/.../compressed → camera_writer.py → /tmp/camera_front.jpg → robot_server → WebUI
```

- `camera_writer.py` 是独立的 rclpy 进程，专门订阅相机 compressed topic 并写入 JPEG 文件
- robot_server v3 不包含任何 rclpy 订阅（相机从文件读，关节从文件读，仅 hand_state 通过 rclpy）
- 完全避免与 teleop 的 DDS 冲突

### WebUI 采集 (`collect_data_web.py`)

**双 WebSocket 架构：**
```
浏览器
  ├── WS1 → localhost:8082 → DataCollector (控制: Connect/Start/Stop/Finish)
  └── WS2 → robot_host:8765 → robot_server (监控: get_observation, 100ms)
```

**采集流程：** Connect → 输入 task → Start (3s 预热) → 自动录制 → Stop (后台 AV1 编码) → Finish

**数据格式（LeRobot）：**

| 字段 | 维度 | 说明 |
|------|------|------|
| `observation.images.front` | 480×640×3 video | 正面 335L 相机 |
| `observation.state` | float32 [8] | L1~L7 弧度 + gripper(0~1) |
| `action` | float32 [8] | L1~L7 弧度 + gripper(0~1) |
| `task` | str | task prompt |

**WebUI 功能：**
- Camera mode: Dual / Front Only
- Resolution: 640×480 / 320×240 / 160×120
- 缺失相机显示灰色 "No camera" 占位符
- 删除 episode 按钮（红色 x）
- 编码中显示 "saving episode..." 状态

---

## 遥操作 (`ros2_control_node`)

### 启动方式（参考 TELEOP_GUIDE.md）
1. 终端 1: `bash ~/Desktop/testing/launch_teleop.sh`
2. 终端 2: `ros2 control switch_controllers --deactivate left_arm_controller --activate left_arm_direct_controller`
3. 终端 3-5: XR 数据源 + 臂遥操作 + 灵巧手

### ArmHardware 激活死锁（关键问题）

`ros2_control_node` 的 `on_activate()` 获取互斥锁后等待 CAN 应答，但 CAN 接收回调需要同一把锁 → 23 个线程全睡在 `futex_wait_queue`。

**触发条件**：每次 CAN 接口被重置后——`modprobe -r gs_usb`、`ip link set can0 down/up`、或 `launch_teleop.sh` 自带的 CAN 初始化步骤。

**唯一成功记录**：arm 断电重开 + 全新 gs_usb 加载 + 首次启动 teleop。之后再重置 CAN 就再也没成功过。

**临时方案**：`can_joint_pub.py` 直接从 CAN 解码关节数据，完全绕过 ros2_control_node。

---

## 训练配置

### 配置文件
添加到 `/opt/workspace/openpi/src/openpi/training/config.py`：

```python
TrainConfig(
    name="pi05_arm_dataset",
    model=pi0_config.Pi0Config(pi05=True),
    data=SimpleDataConfig(
        repo_id="/workspace/data/dataset_1781252003",
        data_transforms=ModelTransformFactory(
            default_prompt="pick up the water bottle and place it on the black tray",
        ),
        model_transforms=ModelTransformFactory(
            default_prompt="pick up the water bottle and place it on the black tray",
        ),
        base_config=DataConfig(
            repack_transforms=_transforms.Group(
                inputs=[
                    _transforms.RepackTransform({
                        "image": {"base_0_rgb": "observation.images.front"},
                        "state": "observation.state",
                        "actions": "action",
                    }),
                    _transforms.ConvertImageChwToHwc(),
                    _transforms.InjectImageMask(),
                ]
            ),
            action_sequence_keys=("action",),
        ),
    ),
    # No weight_loader: train from scratch (random init)
    num_workers=0,
    num_train_steps=1000,
    batch_size=12,
    exp_name="pi05_arm_dataset",
    wandb_enabled=False,
)
```

### 新增的自定义 transforms（`/opt/workspace/openpi/src/openpi/transforms.py`）

| transform | 用途 |
|-----------|------|
| `ConvertImageChwToHwc()` | 将 LeRobot 的 CHW 转为 HWC，float 转 uint8 |
| `InjectImageMask()` | 为 `image` 中的每张相机生成 `image_mask`，缺失相机补零 |

### 数据格式适配

- LeRobot dataset key `action`（单数）→ 模型需要 `actions`（复数），通过 `RepackTransform` 和 `action_sequence_keys=("action",)` 处理
- LeRobot 的 `torch.stack(Column)` bug 打了三处补丁（`_query_hf_dataset`, `__init__` 中的 timestamp 和 episode_index）

### 训练参数
- 模型：pi05 (pi0 + Paligemma), float32（Thor GPU 不支持 bf16）
- Batch size: 12
- 步数: 1000
- 学习率: cosine decay（默认）
- 输出: `/opt/workspace/openpi/checkpoints/pi05_arm_dataset/`
- GPU: NVIDIA Thor (CC 11.0, sm_101 降级), ~2.7s/step

### LeRobot 补丁
`/opt/workspace/openpi/.venv/lib/python3.11/site-packages/lerobot/common/datasets/lerobot_dataset.py` 中三处 `torch.stack` 改为：
```python
torch.stack([torch.as_tensor(t) for t in ...])
```

### 预训练权重下载
pi05_base 权重在 `gs://openpi-assets/checkpoints/pi05_base/params`（公开 GCS）。
通过 `gcsfs` + HTTP_PROXY 下载（`192.168.127.5:7897`）。首次下载约 3GB。
当前训练从随机初始化开始（不下载权重）。

---

## 推理监测 WebUI

### 架构

```
浏览器 localhost:8090 → TCP forwarder → Docker :8090
                                         └── inference_webui.py
                                              ├── ThreadingHTTPServer (SSE + POST + GET)
                                              ├── pi0.5 model (checkpoint 199, 13GB)
                                              └── Policy transforms chian
```

### 模型加载
- 自定义 `.npy` 格式 checkpoint，非 orbax 标准格式
- 加载流程：读取 `params_meta.json` → 逐个加载 51 个 `.npy` 文件（13GB）→ `jax.tree.map` 转 JAX array → `nnx.state(model).replace_by_pure_dict()` → `nnx.merge()`
- 强制 float32（Thor GPU 不支持 bf16）
- JIT 编译首次 ~50s（模型创建 + Policy 创建 + sample_actions JIT）

### 推理流程
1. 浏览器 POST `/infer` 带 prompt
2. 后台线程构建 obs dict: `{"image":{"base_0_rgb": 224×224×3 灰图}, "state":[7 joints+gripper+0×24], "prompt":"..."}`
3. Transforms 链：InjectImageMask → ResizeImages → TokenizePrompt → PadStatesAndActions → Normalize → model_transforms
4. `policy.infer(obs)` → `model.sample_actions(rng, observation)` → `actions[50, 32]`
5. Output transforms 链：Unnormalize → data_transforms.outputs
6. 取 `actions[0, :8]` 作为 pred_joints（7 关节 + gripper）
7. 浏览器轮询 `/result` 直到 `status: "ok"`，显示预测值

### 输出格式
```python
{
  "status": "ok",
  "pred_joints": [-1.31, -1.83, -0.27, -0.64, -0.50, -0.23, -0.69],  # 弧度
  "action_seq": [[step0_L1, step0_L2, ..., step0_gripper], ...],      # 50 steps × 8 dims
  "prompt": "pick up the water bottle",
  "infer_time_ms": 750.4
}
```

### 已知限制
- 使用占位灰图（无相机输入），推理结果仅基于 state + prompt
- 首推理 JIT 编译慢（~30s），后续推理 ~750ms
- HTTP 服务器单机单线程处理 **请求**（ThreadingHTTPServer 多线程），SSE 持续推送

---

## 脚本汇总

| 脚本 | 位置 | 用途 |
|------|------|------|
| `start_data_collection.sh` | `/home/telecontrol/workspace/` | 一键启动远程数据采集服务 |
| `start_collect_web.sh` | `/home/telecontrol/` | 宿主机 WebUI 管理（启停+端口转发） |
| `fix_cameras.sh` | `/home/telecontrol/workspace/` | 远程相机启动（335L 先, 305 后） |
| `can_joint_pub.py` | `/home/telecontrol/workspace/` → `/tmp/` | CAN→关节数据解码器 |
| `hand_state_pub.py` | `/home/telecontrol/workspace/` → `/tmp/` | 灵巧手 SDK 状态发布 |
| `camera_writer.py` | `/home/telecontrol/workspace/` → `/tmp/` | 相机 JPEG → 文件 |
| `collect_data_web.py` | Docker `/opt/workspace/` | WebUI 采集控制 |
| `robot_client.py` | Docker `/opt/workspace/` | LeRobot Robot 协议 WS 客户端 |
| `inference_webui.py` | Docker `/opt/workspace/` | 推理监测 WebUI |

---

## 已知问题

### 1. ArmHardware 激活死锁
每次 CAN 重置后触发，23 线程 futex 死锁。无软件恢复方案。

### 2. 335L USB 不稳定
该主机的 USB3 口被降级到 USB2。335L 在 USB2 上可工作但可能掉线重连。

### 3. robot_server 与 teleop DDS 冲突
rclpy 节点与 teleop 的 DDS participant 冲突。v3 版 `robot_server.py` 已完全移除 rclpy 订阅（全部走文件），但 `hand_state_pub.py` 仍然需要 rclpy。

### 4. grasp_bringup.srv 导入失败
`.so` 库有未定义符号 `set_teach_mode`。用 `hand_state_pub.py` 替代。

### 5. 训练 JIT 编译慢
Thor GPU sm_101 降级模式，pi05 模型 JIT 编译约 5-15 分钟。

### 6. 推理 WebUI 占位图
推理使用纯色灰图，无真实相机输入。模型部分行为可能依赖视觉输入。

### 7. HTTP 服务器单线程阻塞
`ThreadingHTTPServer` 虽为多线程，但 SSE 长连接会占用一个线程。大量并发请求时需扩容。

---

## 当前状态（2026-06-22）

| 组件 | 状态 |
|------|------|
| 关节数据 (CAN 解码) | ✅ 正常工作 ~100Hz |
| 灵巧手 (SDK) | ✅ 正常工作 20Hz |
| Front 相机 (335L) | ⚠️ USB2 降级运行掉线频繁 |
| WebUI 采集 | ✅ 正常工作 |
| Teleop 遥操作 | ❌ ArmHardware 死锁 |
| 训练 (pi05_arm_dataset) | ✅ **200 步完成，checkpoint 199 已保存** |
| 推理 WebUI | ✅ **模型加载正常，推理 ~750ms（非 JIT）** |

### 训练结果
- Loss: 2.644 → 0.575（↓78%）
- Checkpoint: 51 个 `.npy` 文件，13GB
- 保存方式: 流式逐个数组（无大缓冲区，不触发 OOM）

### 推理输出格式
```
actions[50, 32] normalized float32 (±3σ)
  [:, :8] = [L1..L7, gripper]  → denormalize: real = norm * std + mean
  [:, 8:] = 0 (padding)
Denormalized units: radians (joints), 0~1 (gripper)
```

### 推理验证
通过 `inference_webui.py` 验证模型适配正常：
- 使用占位灰图 + prompt 输入
- 模型输出合理的关节角度（~±1.7 rad，在工作范围内）
- 不同 prompt 产生不同输出（模型对语义有响应）
- 推理时间 ~750ms（非 JIT）

### 已知问题
- Docker 内存限制 10.8GiB → checkpoint 保存 OOM → 已修复（`docker update --memory="64g"`）
- orbax `CheckpointManager.save()` 异步保存不 finalize → 替换为流式 numpy 保存

---

## 下一步目标

| 优先级 | 目标 | 方案 |
|--------|------|------|
| P0 | **推理结果 3D 可视化** | three.js 内嵌 WebUI，用 `pred_joints` 驱动 7 连杆铰接臂 |
| P1 | **模型部署到真实机器人** | `serve_policy_float32.py` + `send_action` 下发关节指令 |
| P2 | **更多训练数据** | 采集多样化数据集，从 pi05_base 微调，增加训练步数 |
| P3 | **相机输入支持** | 推理 WebUI 接入远程相机帧，启用视觉条件推理 |

