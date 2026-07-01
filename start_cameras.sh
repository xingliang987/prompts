#!/usr/bin/env bash
# start_cameras.sh — 检测并启动实际连接的 Orbbec 相机
# 在远程机械臂机器上执行（SSH 到 sunrise@192.168.127.24）
set -euo pipefail

source /opt/ros/humble/setup.bash
source /home/sunrise/vision_ws/install/setup.bash

FRONT_SERIAL="CP2G853000G1"
WRIST_SERIAL=""

# 查出所有 Orbbec 相机的 serial
detected_serials=""
for dev in /sys/bus/usb/devices/*/serial; do
  s=$(cat "$dev" 2>/dev/null || true)
  if [ -n "$s" ]; then
    detected_serials="$detected_serials $s"
  fi
done

echo "Detected serials:$detected_serials"

has_front=false
has_wrist=false

for s in $detected_serials; do
  if [ "$s" = "$FRONT_SERIAL" ]; then
    has_front=true
  elif [ -n "$s" ] && [ "$s" != "$FRONT_SERIAL" ] && [ "$s" != "$WRIST_SERIAL" ]; then
    has_wrist=true
    WRIST_SERIAL="$s"
  fi
done

# Kill any existing camera nodes
pkill -f "camera_container" 2>/dev/null || true
pkill -f "orbbec_camera" 2>/dev/null || true
sleep 2

if [ "$has_front" = true ]; then
  echo "Starting front camera (335L, serial=$FRONT_SERIAL)..."
  nohup ros2 launch orbbec_camera gemini_330_series.launch.py \
    camera_name:=camera serial_number:="$FRONT_SERIAL" \
    enable_point_cloud:=false enable_depth:=true \
    depth_width:=640 depth_height:=480 color_width:=640 color_height:=480 color_fps:=10 depth_fps:=10 \
    > /tmp/camera_front.log 2>&1 &
  echo "  front PID: $!"
else
  echo "WARNING: Front camera 335L not detected (expected serial $FRONT_SERIAL)"
fi

if [ "$has_wrist" = true ]; then
  echo "Starting wrist camera (305, serial=$WRIST_SERIAL)..."
  nohup ros2 launch orbbec_camera gemini305.launch.py \
    camera_name:=camera_wrist serial_number:="$WRIST_SERIAL" \
    enable_point_cloud:=false enable_depth:=false \
    color_width:=640 color_height:=480 color_fps:=10 \
    > /tmp/camera_wrist.log 2>&1 &
  echo "  wrist PID: $!"
else
  echo "No wrist camera (305) detected, skipping."
fi

echo "Done."
