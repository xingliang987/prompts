#!/usr/bin/env python3
"""joint_writer.py — Read /joint_states via CLI, write to file.
No rclpy, no persistent DDS subscription.
"""
import subprocess
import ast
import os
import time
import json
import signal
import sys

FILE = "/tmp/joint_positions.json"
STOP = False

def signal_handler(sig, frame):
    global STOP
    STOP = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def read():
    try:
        result = subprocess.run(
            ["ros2", "topic", "echo", "/joint_states", "--once",
             "--field", "position"],
            capture_output=True, timeout=5,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0 and result.stdout.strip():
            vals = ast.literal_eval(result.stdout.decode().strip())
            if isinstance(vals, (list, tuple)) and len(vals) >= 7:
                return list(vals[:7])
    except Exception:
        pass
    return None

os.environ.pop("PYTHONPATH", None)

while not STOP:
    j = read()
    if j:
        with open(FILE, "w") as f:
            json.dump({"joint_positions": j, "ts": time.time()}, f)
    time.sleep(0.1)
