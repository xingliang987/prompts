#!/usr/bin/env python3
"""Quick test - reads ROBOT_HOST env var, defaults to 192.168.127.66."""
import os, sys
sys.path.insert(0, "/workspace")
from robot_client import NetworkRobot

host = os.environ.get("ROBOT_HOST", "192.168.127.66")
robot = NetworkRobot(host, 8765)
robot.connect()
print("Connected!")

obs = robot.capture_observation()
print("Joint state:", obs["observation.state"])
print("Image shape:", obs["observation.images.front"].shape)

obs_dict, act_dict = robot.teleop_step(record_data=True)
print("Obs state:", obs_dict["observation.state"])
print("Action:", act_dict["action"])

robot.disconnect()
print("Done!")
