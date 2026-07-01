#!/usr/bin/env bash
# fix_cameras.sh — 远程执行：先启动 335L（带 serial 过滤锁定/UVC 设备），再启动 305
# 保证 335L 始终在 /camera 话题，305 在 /camera_wrist 话题
set -eu

HOST="${1:-sunrise@192.168.127.24}"
PASS="${2:-sunrise}"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$HOST" bash -s <<'REMOTE'
set -eu

set +u
source /opt/ros/humble/setup.bash
source /home/sunrise/vision_ws/install/setup.bash
set -u

# 1. Kill old processes
echo "=== Killing old processes ==="
pkill -9 -f "orbbec_camera" 2>/dev/null || true
pkill -9 -f "camera_container" 2>/dev/null || true
pkill -9 -f "robot_server" 2>/dev/null || true
sleep 3

# 2. Start front 335L FIRST (serial filter locks it to /camera)
echo "=== Starting front 335L ==="
nohup ros2 launch orbbec_camera gemini_330_series.launch.py \
  camera_name:=camera serial_number:=CP2G853000G1 \
  enable_point_cloud:=false enable_depth:=true \
  depth_width:=640 depth_height:=480 color_width:=640 color_height:=480 \
  color_fps:=10 depth_fps:=10 \
  > /tmp/camera_front.log 2>&1 &
echo "Front PID: $!"

sleep 10

# 3. Start wrist 305 SECOND (335L already claimed, only gets real 305)
echo "=== Starting wrist 305 ==="
nohup ros2 launch orbbec_camera gemini305.launch.py \
  camera_name:=camera_wrist \
  enable_point_cloud:=false enable_depth:=false \
  color_width:=640 color_height:=480 color_fps:=10 \
  > /tmp/camera_wrist.log 2>&1 &
echo "Wrist PID: $!"

sleep 5

# 4. Start robot_server
echo "=== Starting robot_server ==="
set +u
source /opt/ros/humble/setup.bash
source /home/sunrise/ros2_ws/install/setup.bash
source /home/sunrise/calibration_ws/install/setup.bash
set -u
nohup python3 /home/sunrise/robot_server.py --port 8765 > /tmp/robot_server.log 2>&1 &
echo "Server PID: $!"

sleep 3
echo "=== Topics ==="
set +u; source /opt/ros/humble/setup.bash; set -u
timeout 5 ros2 topic list | grep camera || true
echo "=== Done ==="
REMOTE
