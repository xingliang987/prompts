#!/usr/bin/env python3
"""can_joint_pub.py — 从 can0 读取 MIT 协议反馈帧，写入共享文件。
不创建 ROS2 节点，不和 teleop 抢 DDS 资源。
"""
import socket
import struct
import time
import json
import os

CAN_IFACE = "can0"
MIT_POS_MIN = -12.57
MIT_POS_MAX = 12.57
JOINT_FILE = "/tmp/joint_positions.json"


def raw_to_rad(raw: int) -> float:
    return raw / 65535.0 * (MIT_POS_MAX - MIT_POS_MIN) + MIT_POS_MIN


def setup_can():
    s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    try:
        s.bind((CAN_IFACE,))
        s.settimeout(0.05)
        return s
    except OSError as e:
        print(f"CAN bind error: {e}")
        return None


def read_frame(sock):
    try:
        frames = sock.recv(32)
        can_id = struct.unpack("<I", frames[:4])[0] & 0x1FFFFFFF
        data = frames[8:16]
        return can_id, data
    except socket.timeout:
        return None
    except Exception:
        return None


def parse_feedback(can_id: int, data: bytes):
    frame_type = (can_id >> 24) & 0x1F
    if frame_type != 0x02:
        return None, None
    motor_id = (can_id >> 8) & 0xFF
    position_raw = (data[0] << 8) | data[1]
    return motor_id, raw_to_rad(position_raw)


def main():
    sock = setup_can()
    if sock is None:
        return

    positions = [0.0] * 7
    updated = [False] * 7
    last_file_write = 0

    while True:
        for _ in range(50):
            frame = read_frame(sock)
            if frame is None:
                break
            can_id, data = frame
            mid, pos = parse_feedback(can_id, data)
            if mid is not None and 1 <= mid <= 7:
                positions[mid - 1] = pos
                updated[mid - 1] = True

        now = time.time()
        if any(updated) and now - last_file_write >= 0.01:
            with open(JOINT_FILE, "w") as f:
                json.dump({
                    "joint_positions": list(positions),
                    "ts": now,
                }, f)
            last_file_write = now
            updated = [False] * 7

        time.sleep(0.001)


if __name__ == "__main__":
    main()
