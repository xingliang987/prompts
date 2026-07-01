#!/usr/bin/env python3
"""robot_client.py — LeRobot Robot Wrapper (网络版)

在 pi0.5 / LeRobot 环境中运行，通过 WebSocket 连接远程机械臂控制机器，
实现 LeRobot 的 Robot 协议接口，可用于数据采集和模型推理。

使用方式:
  python3 -c "from robot_client import NetworkRobot; r = NetworkRobot()  # 读取 ROBOT_HOST 环境变量; r.connect(); print(r.capture_observation())"

采集脚本示例:
  from robot_client import NetworkRobot
  from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

  robot = NetworkRobot()  # 默认读取 $ROBOT_HOST
  robot.connect()

  dataset = LeRobotDataset.create(
      repo_id="my_arm_dataset", fps=10, robot=robot, use_videos=True
  )
  for ep in range(50):
      # 每 episode 开始前预热几秒
      for _ in range(20):
          robot.teleop_step(record_data=False)
          time.sleep(0.1)

      start = time.time()
      while time.time() - start < 30:
          obs, act = robot.teleop_step(record_data=True)
          dataset.add_frame({**obs, **act, "task": "pick up the red cube"})
          time.sleep(0.1)

      dataset.save_episode()
  robot.disconnect()
"""

import asyncio
import json
import os
import time
import threading
from dataclasses import dataclass, field

import numpy as np
import cv2
import torch

import websockets.sync.client as ws_sync


class _CameraInfo:
    """Minimal camera stub for LeRobot compatibility."""
    def __init__(self, width=640, height=480, fps=10, channels=3):
        self.width = width
        self.height = height
        self.fps = fps
        self.channels = channels


@dataclass
class NetworkRobot:
    """LeRobot Robot 协议的网络实现。

    通过 WebSocket 连接到远程 robot_server.py，
    读取关节状态和图像，发送动作指令。
    """

    host: str = os.environ.get("ROBOT_HOST", "192.168.127.66")
    port: int = 8765
    camera_width: int = 640
    camera_height: int = 480

    # state/action 维度
    state_dim: int = 8  # 7 关节 + 1 夹爪
    action_dim: int = 8

    # LeRobot 需要的属性
    robot_type: str = "network_arm"
    is_connected: bool = False

    def __post_init__(self):
        self._ws = None
        self._lock = threading.Lock()
        self._gripper_state = 0.0  # 夹爪状态 (0=全开, 1=全关)
        # LeRobot features 描述
        self.features = self._build_features()

    def _build_features(self) -> dict:
        return {
            "observation.images.front": {
                "dtype": "video",
                "shape": (self.camera_height, self.camera_width, 3),
                "names": ["height", "width", "channels"],
            },
            "observation.images.wrist": {
                "dtype": "video",
                "shape": (self.camera_height, self.camera_width, 3),
                "names": ["height", "width", "channels"],
            },
            "observation.state": {
                "dtype": "float32",
                "shape": (self.state_dim,),
                "names": [f"L{i}_joint" for i in range(1, 8)] + ["gripper"],
            },
            "action": {
                "dtype": "float32",
                "shape": (self.action_dim,),
                "names": [f"L{i}_joint" for i in range(1, 8)] + ["gripper"],
            },
        }

    # ── LeRobot 兼容属性 ───────────────────────────────────────────

    @property
    def cameras(self) -> dict:
        """LeRobot 需要: 字典值需有 fps/width/height/channels 属性。"""
        return {
            "front": _CameraInfo(width=self.camera_width, height=self.camera_height, fps=10),
            "wrist": _CameraInfo(width=self.camera_width, height=self.camera_height, fps=10),
        }

    @property
    def camera_features(self) -> dict:
        return {
            "observation.images.front": self.features["observation.images.front"],
            "observation.images.wrist": self.features["observation.images.wrist"],
        }

    @property
    def motor_features(self) -> dict:
        return {
            "observation.state": self.features["observation.state"],
            "action": self.features["action"],
        }

    # ── LeRobot Robot 协议方法 ──────────────────────────────────

    def connect(self):
        """连接到远程 WebSocket 服务器。"""
        if self.is_connected:
            return
        uri = f"ws://{self.host}:{self.port}"
        self._ws = ws_sync.connect(uri, open_timeout=10)
        self.is_connected = True
        print(f"已连接到 {uri}")

    def run_calibration(self):
        """标定 — 远程机器已处理，这里不需要做。"""
        pass

    def teleop_step(self, record_data=False):
        """遥操作一步。

        在 record 模式下，从远程读取状态和图像，返回 (obs, action)。
        action 需要由 VR/外部输入提供，这里返回零动作占位。
        """
        if not self.is_connected:
            raise RuntimeError("未连接，请先调用 connect()")

        obs = self._request_observation()

        if not record_data:
            return

        # action: 由 VR 系统提供，这里用当前状态作为占位
        # 实际使用时，VR 数据应该替换这行
        state = obs["joint_positions"]
        gripper = obs["gripper_state"]
        if state is None:
            state = np.zeros(7, dtype=np.float32)
        state = np.append(state, gripper).astype(np.float32)

        dummy_action = np.zeros(self.action_dim, dtype=np.float32)
        jp = obs["joint_positions"]
        if jp is not None:
            dummy_action[:7] = jp
        dummy_action[7] = gripper

        return (
            {
                "observation.state": torch.from_numpy(state),
                "observation.images.front": torch.from_numpy(obs["image"]),
                "observation.images.wrist": torch.from_numpy(obs["wrist_image"]),
            },
            {"action": torch.from_numpy(dummy_action).float()},
        )

    def capture_observation(self):
        """读取当前观察（推理模式下使用）。"""
        if not self.is_connected:
            raise RuntimeError("未连接，请先调用 connect()")

        obs = self._request_observation()
        state = obs["joint_positions"]
        gripper = obs["gripper_state"]
        if state is None:
            state = np.zeros(7, dtype=np.float32)
        state = np.append(state, gripper).astype(np.float32)

        return {
            "observation.state": torch.from_numpy(state),
            "observation.images.front": torch.from_numpy(obs["image"]),
            "observation.images.wrist": torch.from_numpy(obs["wrist_image"]),
        }

    def send_action(self, action: torch.Tensor) -> torch.Tensor:
        """发送动作到远程机械臂执行。"""
        if not self.is_connected:
            raise RuntimeError("未连接")

        action_np = action.numpy().tolist()
        joint_positions = action_np[:7]
        gripper = action_np[-1] if len(action_np) >= 8 else None

        msg = json.dumps({
            "type": "send_action",
            "joint_positions": joint_positions,
            "gripper": gripper,
        })

        with self._lock:
            self._ws.send(msg)
            result = json.loads(self._ws.recv())

        if not result.get("success", False):
            print(f"动作执行警告: {result.get('errors', '')}")

        # 根据发送的 gripper 命令更新追踪状态
        # 阈值和 robot_server.py 一致
        if gripper is not None:
            if gripper > 0.6:
                self._gripper_state = 1.0
            elif gripper < 0.4:
                self._gripper_state = 0.0
            # 中间值保持上次状态不变

        return action  # 返回原始 action（未限幅）

    def disconnect(self):
        """断开连接。"""
        if self._ws is not None:
            self._ws.close()
        self.is_connected = False

    # ── 内部方法 ────────────────────────────────────────────────

    def _request_observation(self) -> dict:
        """向远程请求关节状态和图像。"""
        with self._lock:
            self._ws.send(json.dumps({"type": "get_observation"}))
            meta = json.loads(self._ws.recv())

            raw = meta.get("joint_positions")
            if raw is not None and all(v is not None for v in raw):
                joint_positions = np.array(raw, dtype=np.float32)
            else:
                joint_positions = np.zeros(7, dtype=np.float32)

            def recv_jpeg(flag_key: str):
                if meta.get(flag_key, False):
                    jpeg_data = self._ws.recv()
                    if isinstance(jpeg_data, bytes):
                        img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                        decoded = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if decoded is not None:
                            return cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
                return np.zeros((self.camera_height, self.camera_width, 3), dtype=np.uint8)

            image = recv_jpeg("has_front_image")
            wrist_image = recv_jpeg("has_wrist_image")

        # 用 hand_state[0] 硬件读数替代软件追踪值
        hs = meta.get("hand_state")
        if hs and len(hs) > 0 and hs[0] is not None:
            gripper = hs[0] / 255.0  # 255→1.0(张开), 0→0.0(闭合)
            self._gripper_state = gripper

        return {"joint_positions": joint_positions, "image": image, "wrist_image": wrist_image, "gripper_state": self._gripper_state}

    def __del__(self):
        try:
            self.disconnect()
        except Exception:
            pass


# ── 直接使用示例 ─────────────────────────────────────────────────

def test_connection():
    """快速测试：连接远程机器人并打印状态。"""
    robot = NetworkRobot()  # 默认读取 $ROBOT_HOST
    try:
        robot.connect()
        print("连接成功！")

        obs = robot.capture_observation()
        print(f"关节状态: {obs['observation.state']}")
        print(f"图像: {obs['observation.images.front'].shape}")

        # 读取 info
        robot._ws.send(json.dumps({"type": "get_info"}))
        info = json.loads(robot._ws.recv())
        print(f"机器人信息: {info}")
    finally:
        robot.disconnect()


if __name__ == "__main__":
    test_connection()
