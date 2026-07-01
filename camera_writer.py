#!/usr/bin/env python3
"""camera_writer.py — 订阅相机 compressed topic 并写入文件。
单独运行，不依赖 robot_server 的 CameraCache。
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
import threading

FRONT_FILE = "/tmp/camera_front.jpg"
WRIST_FILE = "/tmp/camera_wrist.jpg"


class CameraWriter(Node):
    def __init__(self):
        super().__init__("camera_writer")
        self._lock = threading.Lock()
        self._front = None
        self._wrist = None

        self.create_subscription(
            CompressedImage, "/camera/color/image_raw/compressed",
            lambda msg: self._save("front", msg), 1)
        self.create_subscription(
            CompressedImage, "/camera_wrist/color/image_raw/compressed",
            lambda msg: self._save("wrist", msg), 1)

        self._timer = self.create_timer(0.05, self._flush)

    def _save(self, cam: str, msg: CompressedImage):
        with self._lock:
            if cam == "front":
                self._front = bytes(msg.data)
            else:
                self._wrist = bytes(msg.data)

    def _flush(self):
        with self._lock:
            if self._front:
                with open(FRONT_FILE, "wb") as f:
                    f.write(self._front)
                self._front = None
            if self._wrist:
                with open(WRIST_FILE, "wb") as f:
                    f.write(self._wrist)
                self._wrist = None


def main():
    rclpy.init()
    node = CameraWriter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
