#!/usr/bin/env bash
# start_all.sh — 全组件统一管理脚本
# 管理本机 Docker 容器内的 WebUI 服务 + 端口转发 + 远程机器人服务
set -euo pipefail

# ═══════════════════════ Configuration ═══════════════════════
CONTAINER_NAME="${CONTAINER_NAME:-pi}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/opt/workspace}"
DATA_HTTP_PORT="${DATA_HTTP_PORT:-8081}"
DATA_WS_PORT="${DATA_WS_PORT:-8082}"
INFER_PORT="${INFER_PORT:-8090}"
ROBOT_HOST="${ROBOT_HOST:-192.168.31.11}"
ROBOT_PORT="${ROBOT_PORT:-8765}"
REMOTE_USER="${REMOTE_USER:-sunrise}"
REMOTE_PASS="${REMOTE_PASS:-sunrise}"
LOG_DIR_HOST="${LOG_DIR_HOST:-/home/telecontrol/workspace/logs}"   # host path
LOG_DIR_CTR="${LOG_DIR_CTR:-/opt/workspace/logs}"                  # container path
FORWARD_SCRIPT_DIR="${FORWARD_SCRIPT_DIR:-/tmp}"

# Python venv path inside container
VENV_PYTHON="/opt/workspace/openpi/.venv/bin/python3"

# ═══════════════════════ Helpers ═════════════════════════════

usage() {
  cat <<USAGE
Usage: $0 <command> [options]

Commands (local services):
  data-collection start       启动数据采集 WebUI (ports ${DATA_HTTP_PORT}/${DATA_WS_PORT})
  data-collection stop        停止数据采集 WebUI + 端口转发
  inference start             启动推理监测 WebUI (port ${INFER_PORT})
  inference stop              停止推理监测 WebUI + 端口转发
  forwarder <port> start      启动指定端口的 TCP 转发
  forwarder <port> stop       停止指定端口的 TCP 转发

Commands (remote robot services via SSH):
  remote start                启动远程机器所有服务（相机 + CAN + 手 + robot_server）
  remote stop                 停止远程机器所有服务

Commands (all-in-one):
  start                       启动所有本机服务 + 远程服务
  stop                        停止所有本机服务
  status                      查看所有服务状态
  logs                        查看所有日志
  help                        显示本帮助

Environment overrides:
  CONTAINER_NAME=${CONTAINER_NAME}
  ROBOT_HOST=${ROBOT_HOST} (远程机器 IP)
  REMOTE_USER=${REMOTE_USER} (远程 SSH 用户名)
  REMOTE_PASS=${REMOTE_PASS} (远程 SSH 密码)
  DATA_HTTP_PORT=${DATA_HTTP_PORT} / DATA_WS_PORT=${DATA_WS_PORT} / INFER_PORT=${INFER_PORT}

Examples:
  $0 data-collection start     # 启动数据采集
  $0 inference start           # 启动推理监测
  $0 start                     # 启动全部
  $0 status                    # 查看状态
USAGE
}

# ── Logging ──
log_info()  { echo "[INFO]  $*"; }
log_warn()  { echo "[WARN]  $*" >&2; }
log_error() { echo "[ERROR] $*" >&2; }

container_ip() {
  docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CONTAINER_NAME}" 2>/dev/null || true
}

container_exec() {
  docker exec "${CONTAINER_NAME}" bash -lc "$*" 2>/dev/null || true
}

container_exec_detach() {
  docker exec -d "${CONTAINER_NAME}" bash -lc "$*" >/dev/null 2>&1 || true
}

ensure_docker() {
  if ! docker ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_error "Container '${CONTAINER_NAME}' is not running. Start it with: docker start ${CONTAINER_NAME}"
    return 1
  fi
}

# ═══════════════════════ Forwarder ═══════════════════════════
# Reuses the same forwarder mechanism as start_collect_web.sh

forward_script_file() { echo "${FORWARD_SCRIPT_DIR}/forward_${1}.py"; }
forward_pid_file()    { echo "${FORWARD_SCRIPT_DIR}/forward_${1}.pid"; }
forward_log_file()    { echo "${FORWARD_SCRIPT_DIR}/forward_${1}.log"; }

_write_forwarder_script() {
  local port="$1"
  local fscript
  fscript="$(forward_script_file "${port}")"
  if [[ -f "${fscript}" ]]; then return 0; fi
  cat > "${fscript}" <<'PYEOF'
import socket, sys, threading
T=(sys.argv[1],int(sys.argv[2])); L=('0.0.0.0',int(sys.argv[3]))
def p(l,r):
 while True:
  try:
   d=l.recv(65536)
   if not d:break
   r.sendall(d)
  except:break
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(L); s.listen(128)
while True:
 c,_=s.accept()
 try:u=socket.create_connection(T,timeout=10);threading.Thread(target=p,args=(c,u),daemon=True).start();threading.Thread(target=p,args=(u,c),daemon=True).start()
 except:c.close()
PYEOF
}

forwarder_start() {
  local port="$1"
  local ip
  ip="$(container_ip)"
  if [[ -z "${ip}" ]]; then
    log_error "Cannot determine container IP"
    return 1
  fi
  # Kill any existing forwarder on this port
  local old_pid_file old_pid
  old_pid_file="$(forward_pid_file "${port}")"
  if [[ -f "${old_pid_file}" ]]; then
    old_pid="$(cat "${old_pid_file}" 2>/dev/null || true)"
    if [[ -n "${old_pid}" ]]; then
      kill "${old_pid}" 2>/dev/null || true
      sleep 1
    fi
    rm -f "${old_pid_file}"
  fi
  _write_forwarder_script "${port}"
  local fscript fpid flog
  fscript="$(forward_script_file "${port}")"
  fpid="$(forward_pid_file "${port}")"
  flog="$(forward_log_file "${port}")"
  rm -f "${flog}"
  nohup python3 "${fscript}" "${ip}" "${port}" "${port}" > "${flog}" 2>&1 &
  echo "$!" > "${fpid}"
  sleep 1
  if ! kill -0 "$(cat "${fpid}")" 2>/dev/null; then
    log_error "Forwarder :${port} failed to start."
    cat "${flog}" >&2 || true
    return 1
  fi
  log_info "Forwarder :${port} -> ${ip}:${port} started (pid $(cat "${fpid}"))"
}

forwarder_stop() {
  local port="$1"
  local pid_file fpid
  pid_file="$(forward_pid_file "${port}")"
  if [[ -f "${pid_file}" ]]; then
    fpid="$(cat "${pid_file}" 2>/dev/null || true)"
    if [[ -n "${fpid}" ]]; then
      kill "${fpid}" 2>/dev/null || true
      sleep 1
      kill -KILL "${fpid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
  fi
  log_info "Forwarder :${port} stopped"
}

# ═══════════════════════ Data Collection WebUI ═══════════════

_data_collection_pidfile() { echo "${LOG_DIR_HOST}/collect_data_web.pid"; }

data_collection_start() {
  ensure_docker || return 1
  log_info "Starting data collection WebUI..."
  mkdir -p "${LOG_DIR_HOST}" && docker exec "${CONTAINER_NAME}" mkdir -p "${LOG_DIR_CTR}"
  local pidfile
  pidfile="$(_data_collection_pidfile)"
  # Kill old server
  container_exec "pkill -f 'collect_data_web.py' 2>/dev/null || true"
  rm -f "${pidfile}"
  container_exec_detach \
    "cd '${WORKSPACE_DIR}'; nohup '${VENV_PYTHON}' '${WORKSPACE_DIR}/collect_data_web.py' \
      --http-port='${DATA_HTTP_PORT}' --ws-port='${DATA_WS_PORT}' \
      --robot-host='${ROBOT_HOST}' --robot-port='${ROBOT_PORT}' \
      > '${LOG_DIR_CTR}/collect_data_web.log' 2>&1 &"
  echo "started" > "${pidfile}"
  log_info "Checking server... (up to 30s)"
  for _ in $(seq 1 30); do
    if container_exec "curl -fsS --max-time 1 http://127.0.0.1:${DATA_HTTP_PORT} >/dev/null 2>&1"; then
      log_info "Data collection WebUI ready at http://localhost:${DATA_HTTP_PORT}"
      forwarder_start "${DATA_HTTP_PORT}"
      forwarder_start "${DATA_WS_PORT}"
      return 0
    fi
    sleep 1
  done
  log_error "Data collection WebUI did not become ready. Check logs."
  tail -20 "${LOG_DIR_CTR}/collect_data_web.log" 2>/dev/null || true
  return 1
}

data_collection_stop() {
  log_info "Stopping data collection WebUI..."
  forwarder_stop "${DATA_WS_PORT}"
  forwarder_stop "${DATA_HTTP_PORT}"
  container_exec "pkill -f 'collect_data_web.py' 2>/dev/null || true"
  rm -f "$(_data_collection_pidfile)"
  log_info "Data collection WebUI stopped"
}

# ═══════════════════════ Inference WebUI ═════════════════════

_infer_pidfile() { echo "${LOG_DIR_HOST}/inference_webui.pid"; }

inference_start() {
  ensure_docker || return 1
  mkdir -p "${LOG_DIR_HOST}" && docker exec "${CONTAINER_NAME}" mkdir -p "${LOG_DIR_CTR}"
  local pidfile
  pidfile="$(_infer_pidfile)"
  log_info "Starting inference WebUI..."
  mkdir -p "${LOG_DIR_HOST}" && docker exec "${CONTAINER_NAME}" mkdir -p "${LOG_DIR_CTR}"
  local pidfile
  pidfile="$(_infer_pidfile)"
  # Kill old server
  container_exec "pkill -f 'inference_webui.py' 2>/dev/null || true"
  rm -f "${pidfile}"
  container_exec_detach \
    "cd '${WORKSPACE_DIR}'; nohup '${VENV_PYTHON}' '${WORKSPACE_DIR}/inference_webui.py' \
      --port='${INFER_PORT}' \
      > '${LOG_DIR_CTR}/inference_webui.log' 2>&1 &"
  echo "started" > "${pidfile}"
  log_info "Waiting for model to load (JIT ~50s)..."
  # Wait for it to respond (model may take a while to load)
  for _ in $(seq 1 120); do
    if container_exec "curl -fsS --max-time 2 http://127.0.0.1:${INFER_PORT} >/dev/null 2>&1"; then
      log_info "Inference WebUI HTTP server ready"
      forwarder_start "${INFER_PORT}"
      log_info "Inference WebUI at http://localhost:${INFER_PORT}"
      log_info "Model loading continues in background (check SSE for 'model_loaded': true)"
      return 0
    fi
    sleep 2
  done
  log_warn "Inference WebUI HTTP server started but model may still be loading."
  log_warn "Check http://localhost:${INFER_PORT} and wait for 'loading model...' to clear."
  forwarder_start "${INFER_PORT}"
  return 0
}

inference_stop() {
  log_info "Stopping inference WebUI..."
  forwarder_stop "${INFER_PORT}"
  container_exec "pkill -f 'inference_webui.py' 2>/dev/null || true"
  rm -f "$(_infer_pidfile)"
  log_info "Inference WebUI stopped"
}

# ═══════════════════════ Remote Services ═════════════════════

remote_start() {
  log_info "Starting remote services on ${REMOTE_USER}@${ROBOT_HOST}..."
  log_warn "Make sure the robot is powered on and CAN bus is configured."
  log_warn "This will SSH into the remote machine and launch services."
  echo ""

  sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "${REMOTE_USER}@${ROBOT_HOST}" bash -s <<'REMOTESCRIPT'
set -eu
LOGDIR=/tmp
echo "[Remote] Starting services..."

# 0. Kill old processes
pkill -f "can_joint_pub.py" 2>/dev/null || true
pkill -f "hand_state_pub.py" 2>/dev/null || true
pkill -f "camera_writer.py" 2>/dev/null || true
pkill -f "robot_server.py" 2>/dev/null || true
pkill -f "ros2 launch" 2>/dev/null || true
pkill -f "ros2" 2>/dev/null || true
sleep 2

# 1. CAN setup
echo "[Remote]   Setting up CAN..."
sudo ip link set can0 up type can bitrate 1000000 dbitrate 5000000 fd on 2>/dev/null || true
sudo ip link set can1 up type can bitrate 1000000 dbitrate 5000000 fd on 2>/dev/null || true
sudo ip link set can0 txqueuelen 1000 2>/dev/null || true
sudo ip link set can1 txqueuelen 1000 2>/dev/null || true
sleep 1

# 2. Cameras (335L first, then 305)
echo "[Remote]   Starting cameras..."
source /opt/ros/humble/setup.bash 2>/dev/null || true
source /home/sunrise/vision_ws/install/setup.bash 2>/dev/null || true
nohup ros2 launch orbbec_camera gemini_330_series.launch.py \
  camera_name:=camera serial_number:=CP2G853000G1 \
  enable_point_cloud:=false enable_depth:=true \
  depth_width:=640 depth_height:=480 color_width:=640 color_height:=480 \
  color_fps:=10 depth_fps:=10 \
  > ${LOGDIR}/camera_front.log 2>&1 &
echo "[Remote]   Front camera PID: $!"
sleep 10
nohup ros2 launch orbbec_camera gemini305.launch.py \
  camera_name:=camera_wrist enable_point_cloud:=false enable_depth:=false \
  color_width:=640 color_height:=480 color_fps:=10 \
  > ${LOGDIR}/camera_wrist.log 2>&1 &
echo "[Remote]   Wrist camera PID: $!"
sleep 5

# 3. CAN joint decoder (no rclpy, reads MIT protocol from can0)
echo "[Remote]   Starting CAN joint decoder..."
python3 /tmp/can_joint_pub.py &
echo "[Remote]   CAN joint PID: $!"
sleep 1

# 4. Hand state publisher (LinkerHand SDK)
echo "[Remote]   Starting hand state publisher..."
source /opt/ros/humble/setup.bash 2>/dev/null || true
source /home/sunrise/ros2_ws/install/setup.bash 2>/dev/null || true
source /home/sunrise/calibration_ws/install/setup.bash 2>/dev/null || true
python3 /tmp/hand_state_pub.py &
echo "[Remote]   Hand PID: $!"
sleep 2

# 5. WebSocket bridge (robot_server)
echo "[Remote]   Starting robot_server..."
nohup python3 /home/sunrise/robot_server.py --port 8765 > ${LOGDIR}/robot_server.log 2>&1 &
echo "[Remote]   robot_server PID: $!"
sleep 3

# 6. Verify
echo "[Remote]   === Verification ==="
echo "[Remote]   joints: $(cat /tmp/joint_positions.json 2>/dev/null | head -c 80 || echo 'waiting...')"
echo "[Remote]   server port: $(ss -tlnp 2>/dev/null | grep 8765 | grep -o 'pid=[0-9]*' || echo 'not found')"
echo "[Remote]   CAN: $(ip -s -d link show can0 2>/dev/null | head -3)"
echo "[Remote] All remote services started."
REMOTESCRIPT
  log_info "Remote services script completed."
  log_info "Connect via WebUI at http://localhost:${DATA_HTTP_PORT}"
}

remote_stop() {
  log_info "Stopping remote services..."
  sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "${REMOTE_USER}@${ROBOT_HOST}" bash -s <<'REMOTESCRIPT'
echo "[Remote] Stopping all services..."
pkill -f "robot_server.py" 2>/dev/null || true
pkill -f "can_joint_pub.py" 2>/dev/null || true
pkill -f "hand_state_pub.py" 2>/dev/null || true
pkill -f "camera_writer.py" 2>/dev/null || true
pkill -f "ros2 launch" 2>/dev/null || true
pkill -f "ros2" 2>/dev/null || true
sleep 2
echo "[Remote] Services stopped."
REMOTESCRIPT
  log_info "Remote services stopped."
}

# ═══════════════════════ Status / Logs ═══════════════════════

cmd_status() {
  echo "══════════════════════════ Service Status ══════════════════════════"
  echo ""

  echo "── Container ─────────────────────────────────────────────────────"
  docker ps --filter "name=^/${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || echo "not running"

  echo ""
  echo "── Data Collection WebUI ─────────────────────────────────────────"
  if container_exec "ps -eo pid,stat,etime,rss,cmd | grep collect_data_web | grep -v grep" 2>/dev/null | grep -q collect; then
    echo "  Status: RUNNING"
    container_exec "ps -eo pid,stat,etime,rss,cmd | grep collect_data_web | grep -v grep" 2>/dev/null
    echo "  URL: http://localhost:${DATA_HTTP_PORT}"
  else
    echo "  Status: STOPPED"
  fi

  echo ""
  echo "── Inference WebUI ───────────────────────────────────────────────"
  if container_exec "ps -eo pid,stat,etime,rss,cmd | grep inference_webui | grep -v grep" 2>/dev/null | grep -q inference; then
    echo "  Status: RUNNING"
    container_exec "ps -eo pid,stat,etime,rss,cmd | grep inference_webui | grep -v grep" 2>/dev/null
    echo "  URL: http://localhost:${INFER_PORT}"
    # Also show model_loaded status
    local infer_status
    infer_status=$(container_exec "curl -fsS --max-time 3 http://127.0.0.1:${INFER_PORT}/events 2>/dev/null | head -1" 2>/dev/null || true)
    if echo "${infer_status}" | grep -q "model_loaded.*true"; then
      echo "  Model: LOADED"
    elif echo "${infer_status}" | grep -q "model_loaded.*false"; then
      echo "  Model: LOADING..."
    fi
  else
    echo "  Status: STOPPED"
  fi

  echo ""
  echo "── Port Forwarders ───────────────────────────────────────────────"
  for port in "${DATA_HTTP_PORT}" "${DATA_WS_PORT}" "${INFER_PORT}"; do
    local pid_file fpid
    pid_file="$(forward_pid_file "${port}")"
    if [[ -f "${pid_file}" ]] && fpid="$(cat "${pid_file}")" && kill -0 "${fpid}" 2>/dev/null; then
      echo "  :${port} -> CONTAINER:${port} (pid=${fpid})"
    else
      echo "  :${port} -> NOT RUNNING"
    fi
  done

  echo ""
  echo "── Remote Robot (${ROBOT_HOST}) ──────────────────────────────────"
  if sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    "${REMOTE_USER}@${ROBOT_HOST}" "ss -tlnp 2>/dev/null | grep -q 8765 && echo 'robot_server: YES' || echo 'robot_server: NO'" 2>/dev/null; then
    echo "  Reachable: YES"
  else
    echo "  Reachable: NO (offline or wrong IP)"
  fi

  echo ""
  echo "── Health Checks ─────────────────────────────────────────────────"
  for port in "${DATA_HTTP_PORT}" "${INFER_PORT}"; do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}" >/dev/null 2>&1; then
      echo "  http://localhost:${port} OK"
    else
      echo "  http://localhost:${port} FAIL"
    fi
  done
}

cmd_logs() {
  echo "═══ Data Collection WebUI ═══"
  cat "${LOG_DIR_CTR}/collect_data_web.log" 2>/dev/null || echo "(no log)"
  echo ""
  echo "═══ Inference WebUI ═══"
  local inf_log
  inf_log=$(container_exec "cat /tmp/inf_webui.log" 2>/dev/null || true)
  if [[ -n "${inf_log}" ]]; then
    echo "${inf_log}" | strings | grep -v "compute capability\|FutureWarning\|Unable to initialize\|import pynvml" | tail -30
  else
    echo "(no log)"
  fi
  echo ""
  for port in "${DATA_HTTP_PORT}" "${DATA_WS_PORT}" "${INFER_PORT}"; do
    local flog
    flog="$(forward_log_file "${port}")"
    if [[ -f "${flog}" ]]; then
      echo "═══ Forwarder :${port} ═══"
      tail -10 "${flog}" 2>/dev/null || true
      echo ""
    fi
  done
}

# ═══════════════════════ Main ════════════════════════════════

main() {
  mkdir -p "${LOG_DIR_HOST}" && docker exec "${CONTAINER_NAME}" mkdir -p "${LOG_DIR_CTR}"

  case "${1:-help}" in
    data-collection)
      case "${2:-}" in
        start) data_collection_start ;;
        stop)  data_collection_stop ;;
        *)     log_error "Usage: $0 data-collection {start|stop}"; exit 2 ;;
      esac
      ;;
    inference)
      case "${2:-}" in
        start) inference_start ;;
        stop)  inference_stop ;;
        *)     log_error "Usage: $0 inference {start|stop}"; exit 2 ;;
      esac
      ;;
    forwarder)
      if [[ $# -lt 3 ]]; then
        log_error "Usage: $0 forwarder <port> {start|stop}"; exit 2
      fi
      case "${3:-}" in
        start) forwarder_start "$2" ;;
        stop)  forwarder_stop "$2" ;;
        *)     log_error "Usage: $0 forwarder <port> {start|stop}"; exit 2 ;;
      esac
      ;;
    remote)
      case "${2:-}" in
        start) remote_start ;;
        stop)  remote_stop ;;
        *)     log_error "Usage: $0 remote {start|stop}"; exit 2 ;;
      esac
      ;;
    start)
      log_info "Starting ALL services..."
      data_collection_start
      inference_start
      log_info "Local services started. Use '$0 remote start' for robot services."
      ;;
    stop)
      log_info "Stopping ALL services..."
      inference_stop
      data_collection_stop
      log_info "All local services stopped."
      log_info "Use '$0 remote stop' to stop remote robot services."
      ;;
    status) cmd_status ;;
    logs)   cmd_logs ;;
    help|--help|-h) usage ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
