#!/usr/bin/env python3
"""hand_state_pub.py — 发布灵巧手状态到 /hand_state 话题。

读取 LinkerHand SDK 的真实手部位置（如果 SDK 可用），
否则发布硬编码占位值 [255, 0, 0, 0, 0, 0]（全开）。

DataCollector 取 hand_state[0]/255 作为夹爪值写入数据集。
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray
import sys
import os

SDK_ROOT = os.environ.get("LINKERHAND_SDK_ROOT", "/home/sunrise/linkerhand-python-sdk")
CAN_IFACE = os.environ.get("LINKERHAND_CAN", "can0")


class HandStatePublisher(Node):
    def __init__(self):
        super().__init__("hand_state_publisher")
        self._hand = None
        self._init_error = ""
        self._try_init_hand()
        self._pub = self.create_publisher(Int32MultiArray, "/hand_state", 1)
        self._timer = self.create_timer(0.05, self._publish)

    def _try_init_hand(self):
        sdk_root = SDK_ROOT
        if sdk_root and sdk_root not in sys.path:
            sys.path.append(sdk_root)
        try:
            from LinkerHand.linker_hand_api import LinkerHandApi
            self._hand = LinkerHandApi(hand_joint="O6", hand_type="left", can=CAN_IFACE)
            self.get_logger().info(f"LinkerHand SDK initialized on {CAN_IFACE}")
        except Exception as e:
            self._init_error = str(e)
            self.get_logger().warn(
                f"LinkerHand SDK not available ({e}), "
                f"publishing dummy [255,0,0,0,0,0]"
            )

    def _read_hand_state(self):
        if self._hand is None:
            return [255, 0, 0, 0, 0, 0]
        try:
            state = self._hand.get_state()
            if state and len(state) >= 6:
                return list(state[:6])
            return [255, 0, 0, 0, 0, 0]
        except Exception:
            return [255, 0, 0, 0, 0, 0]

    def _publish(self):
        msg = Int32MultiArray()
        msg.data = self._read_hand_state()
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = HandStatePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
