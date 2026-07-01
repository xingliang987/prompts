#!/usr/bin/env bash
# start_data_collection.sh — 一键启动远程机器上所有数据采集服务
set -eu

HOST="${1:-sunrise@192.168.127.24}"
PASS="${2:-sunrise}"
SRC="$(dirname "$0")"

echo "=== 0/4 同步脚本到远程 ==="
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$SRC/can_joint_pub.py" "$SRC/hand_state_pub.py" \
  "$HOST:/tmp/" 2>/dev/null
echo "  done"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$HOST" bash -s <<'REMOTE'
set -eu
LOGDIR=/tmp

echo "=== 1/4 启动相机 ==="
set +u
source /opt/ros/humble/setup.bash
source /home/sunrise/vision_ws/install/setup.bash
set -u

# 335L 先
nohup ros2 launch orbbec_camera gemini_330_series.launch.py \
  camera_name:=camera serial_number:=CP2G853000G1 \
  enable_point_cloud:=false enable_depth:=true \
  depth_width:=640 depth_height:=480 color_width:=640 color_height:=480 \
  color_fps:=10 depth_fps:=10 \
  > ${LOGDIR}/camera_front.log 2>&1 &
echo "  front PID: $!"
sleep 10

# 305 后
nohup ros2 launch orbbec_camera gemini305.launch.py \
  camera_name:=camera_wrist \
  enable_point_cloud:=false enable_depth:=false \
  color_width:=640 color_height:=480 color_fps:=10 \
  > ${LOGDIR}/camera_wrist.log 2>&1 &
echo "  wrist PID: $!"
sleep 5

echo "=== 2/4 CAN 关节解码器 ==="
source /opt/ros/humble/setup.bash 2>/dev/null || true
python3 /tmp/can_joint_pub.py &
echo "  can_joint PID: $!"
sleep 1

echo "=== 3/4 灵巧手 SDK ==="
set +u
source /opt/ros/humble/setup.bash
source /home/sunrise/ros2_ws/install/setup.bash
source /home/sunrise/calibration_ws/install/setup.bash
set -u
python3 /tmp/hand_state_pub.py &
echo "  hand PID: $!"
sleep 2

echo "=== 4/4 WebSocket 桥接 ==="
nohup python3 /home/sunrise/robot_server.py --port 8765 > ${LOGDIR}/robot_server.log 2>&1 &
echo "  server PID: $!"
sleep 4

echo "=== 验证 ==="
echo "  joints: $(cat /tmp/joint_positions.json 2>/dev/null | head -c 80 || echo 'waiting...')"
echo "  server: $(ss -tlnp | grep 8765 | grep -o 'pid=[0-9]*')"
echo ""
echo "=== 完成 ==="
echo "浏览器打开 http://localhost:8081"
REMOTE
