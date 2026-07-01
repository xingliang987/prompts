#!/usr/bin/env python3
from __future__ import annotations
import sys, time
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray
from grasp_bringup.srv import ExecuteHandGrasp

class HandGraspServer(Node):
    def __init__(self) -> None:
        super().__init__("hand_grasp_server")
        self.declare_parameter("arm_side", "left")
        self.declare_parameter("can", "can0")
        self.declare_parameter("sdk_root", "/home/sunrise/linkerhand-python-sdk")
        self._arm_side = str(self.get_parameter("arm_side").value).strip().lower()
        self._can = str(self.get_parameter("can").value).strip()
        self._sdk_root = str(self.get_parameter("sdk_root").value).strip()
        self._hand = None
        self._init_error = ""
        self._try_init_hand()
        self.create_service(ExecuteHandGrasp, "/execute_hand_grasp", self._handle_execute_hand_grasp)
        self._state_pub = self.create_publisher(Int32MultiArray, "/hand_state", 1)
        self._timer = self.create_timer(0.05, self._publish_state)

    def _publish_state(self):
        if self._hand is None:
            return
        try:
            state = self._hand.get_state() or [0] * 6
            self._state_pub.publish(Int32MultiArray(data=[int(v) for v in state]))
        except Exception:
            pass

    def _init_hand(self):
        if self._sdk_root and self._sdk_root not in sys.path:
            sys.path.append(self._sdk_root)
        try:
            from LinkerHand.linker_hand_api import LinkerHandApi
        except Exception as exc:
            raise RuntimeError(f"LinkerHandApi import failed: {exc}") from exc
        hand = LinkerHandApi(hand_joint="O6", hand_type=self._arm_side, can=self._can)
        hand.set_speed(speed=[150, 150, 150, 150, 150, 150])
        self.get_logger().info(f"O6 {self._arm_side} hand ready (CAN: {self._can})")
        return hand

    def _try_init_hand(self) -> None:
        try:
            self._hand = self._init_hand()
            self._init_error = ""
        except Exception as exc:
            self._hand = None
            self._init_error = str(exc)
            self.get_logger().warning(f"Hand unavailable: {exc}")

    def _open_logic(self) -> None:
        current = self._hand.get_state() or [0] * 6
        self._hand.finger_move(pose=[255, 255, current[2], current[3], current[4], current[5]])
        time.sleep(0.5)
        self._hand.finger_move(pose=[255] * 6)

    def _close_logic(self) -> None:
        self._hand.finger_move(pose=[255, 255, 0, 0, 0, 0])
        time.sleep(0.5)
        self._hand.finger_move(pose=[0] * 6)

    def _grasp_logic(self) -> None:
        current = self._hand.get_state() or [255] * 6
        self._hand.finger_move(pose=[current[0], 0, current[2], current[3], current[4], current[5]])
        time.sleep(0.5)
        self._hand.finger_move(pose=[255, 0, 0, 0, 0, 0])
        time.sleep(0.5)
        self._hand.finger_move(pose=[0] * 6)

    def _handle_execute_hand_grasp(self, request, response):
        if self._hand is None:
            self._try_init_hand()
        if self._hand is None:
            response.success = False
            response.message = f"Hand unavailable: {self._init_error or 'init failed'}"
            return response
        arm_side = str(request.arm_side).strip().lower()
        if arm_side != self._arm_side:
            response.success = False
            response.message = f"Expected {self._arm_side}, got {arm_side}"
            return response
        grasp_type = str(request.grasp_type).strip().lower()
        try:
            if grasp_type == "open":
                self._open_logic()
            elif grasp_type == "close":
                self._close_logic()
            elif grasp_type == "grasp":
                self._grasp_logic()
            else:
                response.success = False
                response.message = f"Unknown grasp_type: {grasp_type}"
                return response
        except Exception as exc:
            response.success = False
            response.message = f"Hand action failed: {exc}"
            return response
        response.success = True
        response.message = f"Hand action: {grasp_type}"
        return response

    def destroy_node(self) -> bool:
        try:
            if hasattr(self, "_hand") and hasattr(self._hand, "close_can"):
                self._hand.close_can()
        except Exception as exc:
            self.get_logger().warning(f"CAN close failed: {exc}")
        return super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = HandGraspServer()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
