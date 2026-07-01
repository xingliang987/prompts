#!/usr/bin/env python3
"""robot_server.py — ROS2 + WebSocket 桥接服务 (CLI-based, no rclpy)

通过 WebSocket 对外提供机械臂状态读取和动作执行接口。
使用 ros2 CLI 工具代替 rclpy 以避免 FastDDS 内存泄漏。

启动方式：
  source /opt/ros/humble/setup.bash
  source /home/sunrise/ros2_ws/install/setup.bash
  python3 /home/sunrise/robot_server.py [--port 8765] [--host 0.0.0.0]

网络协议：
  - 请求为 JSON 文本帧
  - get_observation 响应: 先发 JSON 帧，再发一帧正面 JPEG（若 has_front_image=true），
    再发一帧夹爪 JPEG（若 has_wrist_image=true）
"""

import asyncio
import json
import argparse
import subprocess
import shlex
import re
import os
import struct
import time
import traceback
import threading
import queue

import numpy as np
import cv2

import websockets
from websockets.asyncio.server import serve

import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from sensor_msgs.msg import CompressedImage, JointState
from std_msgs.msg import Int32MultiArray


def source_env():
    """Source ROS2 env files and return the merged environment dict."""
    env = os.environ.copy()
    for script in [
        "/opt/ros/humble/setup.sh",
        "/home/sunrise/ros2_ws/install/setup.sh",
        "/home/sunrise/calibration_ws/install/setup.sh",
        "/home/sunrise/vision_ws/install/setup.sh",
    ]:
        if os.path.exists(script):
            try:
                out = subprocess.check_output(
                    f'bash -c \'source "{script}" && env\'',
                    shell=True, executable="/bin/bash", timeout=10,
                    stderr=subprocess.DEVNULL,
                ).decode()
                for line in out.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env[k] = v
            except Exception:
                pass
    return env


ROS_ENV = source_env()


class CameraCache:
    """Background rclpy spinner that caches latest camera JPEGs and joint state.

    Uses a single background thread with subscriptions (compressed image + joint state).
    This avoids per-frame subprocess overhead while keeping rclpy isolated.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._front = None
        self._wrist = None
        self._joint_positions = None
        self._hand_state = None
        self._running = False
        self._thread = None
        self._node = None
        self._executor = None

    def start(self):
        if not rclpy.ok():
            rclpy.init()
        self._node = Node("robot_cache")
        self._node.create_subscription(
            CompressedImage, "/camera/color/image_raw/compressed",
            lambda msg: self._on_image("front", msg), 1,
        )
        self._node.create_subscription(
            CompressedImage, "/camera_wrist/color/image_raw/compressed",
            lambda msg: self._on_image("wrist", msg), 1,
        )
        self._node.create_subscription(
            JointState, "/joint_states",
            self._on_joint_state, 1,
        )
        self._node.create_subscription(
            Int32MultiArray, "/hand_state",
            self._on_hand_state, 1,
        )
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _on_image(self, cam: str, msg: CompressedImage):
        with self._lock:
            if cam == "front":
                self._front = bytes(msg.data)
            else:
                self._wrist = bytes(msg.data)

    def _on_joint_state(self, msg: JointState):
        """Cache first 7 joint positions (L1-L7)."""
        with self._lock:
            if len(msg.position) >= 7:
                self._joint_positions = list(msg.position[:7])

    def _on_hand_state(self, msg: Int32MultiArray):
        """Cache hand finger positions."""
        with self._lock:
            self._hand_state = list(msg.data)

    def get_front(self) -> bytes | None:
        with self._lock:
            return self._front

    def get_wrist(self) -> bytes | None:
        with self._lock:
            return self._wrist

    def get_joint_positions(self) -> list[float] | None:
        with self._lock:
            return self._joint_positions

    def get_hand_state(self) -> list[int] | None:
        with self._lock:
            return self._hand_state

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._executor:
            self._executor.remove_node(self._node)
        if self._node:
            self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    def _spin(self):
        while self._running and rclpy.ok():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception:
                pass


def ros2_topic_echo(topic: str, timeout: float = 5.0) -> str | None:
    """Call `ros2 topic echo --once` and return the raw output string."""
    try:
        result = subprocess.run(
            ["ros2", "topic", "echo", topic, "--once", "--no-arr"],
            capture_output=True, text=True, timeout=timeout,
            env=ROS_ENV,
        )
        return result.stdout if result.returncode == 0 else None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def ros2_topic_field(topic: str, field: str, timeout: float = 5.0) -> str | None:
    """Echo a specific field from a ROS2 topic."""
    try:
        out = subprocess.check_output(
            ["ros2", "topic", "echo", topic, "--once", "--field", field],
            timeout=timeout, env=ROS_ENV,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return out
    except Exception:
        return None


def parse_array_output(text: str) -> list[float] | None:
    """Parse 'array('d', [1.0, 2.0, ...])' output from ros2 topic echo --field."""
    if not text:
        return None
    try:
        # Extract the list part between [ and ]
        start = text.index("[")
        end = text.rindex("]")
        nums_str = text[start + 1:end]
        return [float(x.strip()) for x in nums_str.split(",") if x.strip()]
    except (ValueError, IndexError):
        return None



def call_ros_service(service_name: str, service_type: str, args: dict, timeout: float = 15.0) -> dict:
    """Call a ROS2 service using ros2 CLI."""
    args_json = json.dumps(args)
    cmd = [
        "ros2", "service", "call", service_name, service_type, args_json
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env=ROS_ENV,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if result.returncode != 0:
            return {"success": False, "message": stderr[:200]}
        # Parse response - look for the response values
        if "success: true" in stdout or "success=True" in stdout:
            return {"success": True, "message": stdout[:200]}
        elif "success: false" in stdout or "success=False" in stdout:
            return {"success": False, "message": stdout[:200]}
        return {"success": True, "message": stdout[:200]}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "服务调用超时"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


class RobotBridgeCLI:
    """ROS2 bridge using CLI tools + rclpy camera cache."""

    def __init__(self, camera_cache: CameraCache):
        self.camera_cache = camera_cache
        self.joint_names_ordered = [f"L{i}_joint" for i in range(1, 8)]

    def get_observation(self):
        joint_positions = self.camera_cache.get_joint_positions()
        front_jpeg = self.camera_cache.get_front()
        wrist_jpeg = self.camera_cache.get_wrist()
        hand_state = self.camera_cache.get_hand_state()
        return {
            "joint_positions": joint_positions,
            "jpeg_bytes": front_jpeg,
            "wrist_jpeg_bytes": wrist_jpeg,
            "hand_state": hand_state,
        }

    def send_joint_action(self, joint_positions):
        return call_ros_service(
            "/execute_motion_step", "grasp_bringup/srv/ExecuteMotionStep",
            {
                "step_type": "joint",
                "arm_side": "left",
                "plan_only": False,
                "use_bezier": False,
                "joint_positions": [float(v) for v in joint_positions],
            },
            timeout=20.0,
        )

    def send_hand_action(self, command):
        return call_ros_service(
            "/execute_hand_grasp", "grasp_bringup/srv/ExecuteHandGrasp",
            {"grasp_type": command, "arm_side": "left"},
            timeout=10.0,
        )

    def send_stop(self):
        return call_ros_service(
            "/stop_motion", "grasp_bringup/srv/StopMotion",
            {},
            timeout=5.0,
        )


class RobotWebSocketServer:
    def __init__(self, node, host="0.0.0.0", port=8765):
        self.node = node
        self.host = host
        self.port = port
        self.log = print  # simple print-based logging

    async def handle_client(self, websocket):
        self.log(f"新客户端: {websocket.remote_address}")
        try:
            async for raw_msg in websocket:
                try:
                    request = json.loads(raw_msg)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "message": "无效 JSON"}))
                    continue

                req_type = request.get("type", "")

                if req_type == "get_observation":
                    await self._handle_get_observation(websocket)
                elif req_type == "send_action":
                    await self._handle_send_action(websocket, request)
                elif req_type == "hand_action":
                    await self._handle_hand_action(websocket, request)
                elif req_type == "get_info":
                    await self._handle_get_info(websocket)
                elif req_type == "stop":
                    await self._handle_stop(websocket)
                else:
                    await websocket.send(json.dumps({"type": "error", "message": f"未知: {req_type}"}))
        except websockets.exceptions.ConnectionClosed:
            self.log("客户端断开")

    async def _handle_get_observation(self, websocket):
        obs = self.node.get_observation()
        jpeg = obs.pop("jpeg_bytes", None)
        wrist_jpeg = obs.pop("wrist_jpeg_bytes", None)

        meta = {
            "type": "observation",
            "joint_positions": obs["joint_positions"],
            "has_front_image": jpeg is not None,
            "has_wrist_image": wrist_jpeg is not None,
            "hand_state": obs.get("hand_state"),
            "image_width": 640,
            "image_height": 480,
        }
        await websocket.send(json.dumps(meta))
        if jpeg is not None:
            await websocket.send(jpeg)
        if wrist_jpeg is not None:
            await websocket.send(wrist_jpeg)

    async def _handle_send_action(self, websocket, request):
        joint_pos = request.get("joint_positions")
        gripper = request.get("gripper")
        errors = []

        if joint_pos is not None and len(joint_pos) >= 7:
            result = self.node.send_joint_action(joint_pos[:7])
            if not result.get("success", False):
                errors.append(f"关节: {result.get('message', '')}")

        if gripper is not None:
            val = float(gripper)
            if val > 0.6:
                cmd = "close"
            elif val < 0.4:
                cmd = "open"
            else:
                cmd = None
            if cmd:
                result = self.node.send_hand_action(cmd)
                if not result.get("success", False):
                    errors.append(f"夹爪: {result.get('message', '')}")

        await websocket.send(json.dumps({
            "type": "action_result",
            "success": len(errors) == 0,
            "errors": errors,
        }))

    async def _handle_hand_action(self, websocket, request):
        cmd = request.get("command", "open")
        result = self.node.send_hand_action(cmd)
        await websocket.send(json.dumps({"type": "hand_result", **result}))

    async def _handle_get_info(self, websocket):
        await websocket.send(json.dumps({
            "type": "info",
            "robot": "7-DoF Left Arm + LinkerHand",
            "joints": [f"L{i}_joint" for i in range(1, 8)],
            "action_dim": 8,
            "state_dim": 7,
        }))

    async def _handle_stop(self, websocket):
        result = self.node.send_stop()
        await websocket.send(json.dumps({"type": "stop_result", **result}))

    async def start(self):
        self.log(f"WebSocket 服务器启动: {self.host}:{self.port}")
        async with serve(self.handle_client, self.host, self.port):
            await asyncio.get_running_loop().create_future()


def main():
    parser = argparse.ArgumentParser(description="机器人 WebSocket 桥接")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    camera_cache = CameraCache()
    camera_cache.start()
    print("相机缓存已启动")

    node = RobotBridgeCLI(camera_cache)
    server = RobotWebSocketServer(node, host=args.host, port=args.port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
    finally:
        print("正在关闭...")
        camera_cache.stop()


if __name__ == "__main__":
    main()
