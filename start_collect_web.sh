#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-pi}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/opt/workspace}"
HTTP_PORT="${HTTP_PORT:-8081}"
WS_PORT="${WS_PORT:-8082}"
ROBOT_HOST="${ROBOT_HOST:-192.168.31.11}"
ROBOT_PORT="${ROBOT_PORT:-8765}"
SERVER_LOG="${SERVER_LOG:-${WORKSPACE_DIR}/logs/collect_data_web.log}"
FORWARD_SCRIPT_DIR="/tmp"

usage() {
  cat <<USAGE
Usage: $0 [start|stop|restart|status|logs]

Starts the data collection WebUI inside Docker and forwards
host ${HTTP_PORT}:${WS_PORT} to the container's ${HTTP_PORT}:${WS_PORT}.

Environment overrides:
  CONTAINER_NAME=${CONTAINER_NAME}
  HTTP_PORT=${HTTP_PORT}
  WS_PORT=${WS_PORT}
USAGE
}

container_ip() {
  docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CONTAINER_NAME}"
}

container_exec() {
  docker exec "${CONTAINER_NAME}" bash -lc "$*"
}

# ── Forwarder management ──────────────────────────────────────

forward_pid_file() {
  echo "${FORWARD_SCRIPT_DIR}/collect_web_${1}_forward.pid"
}

forward_log_file() {
  echo "${FORWARD_SCRIPT_DIR}/collect_web_${1}_forward.log"
}

forward_script_file() {
  echo "${FORWARD_SCRIPT_DIR}/collect_web_${1}_forward.py"
}

write_forwarder() {
  local port="$1"
  local fscript
  fscript="$(forward_script_file "${port}")"
  if [[ -f "${fscript}" ]]; then
    return 0
  fi
  cat > "${fscript}" <<'PY'
import select, socket, sys, threading

target_host = sys.argv[1]
target_port = int(sys.argv[2])
listen_host  = sys.argv[3]
listen_port  = int(sys.argv[4])

def pipe(left, right):
    sockets = [left, right]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 60)
            if not readable:
                continue
            for sock in readable:
                data = sock.recv(65536)
                if not data:
                    return
                (right if sock is left else left).sendall(data)
    except OSError:
        pass
    finally:
        for sock in sockets:
            try:
                sock.close()
            except OSError:
                pass

def handle(client):
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=10)
    except OSError:
        client.close()
        return
    pipe(client, upstream)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((listen_host, listen_port))
server.listen(128)
print(f"forwarding {listen_host}:{listen_port} -> {target_host}:{target_port}", flush=True)

while True:
    client, _ = server.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()
PY
}

stop_forwarder() {
  local port="$1"
  local pid_file
  pid_file="$(forward_pid_file "${port}")"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}" || true)"
    if [[ -n "${pid}" ]]; then
      kill "${pid}" 2>/dev/null || true
      sleep 1
      kill -KILL "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
  fi
}

start_forwarder() {
  local port="$1"
  local ip
  ip="$(container_ip)"
  if [[ -z "${ip}" ]]; then
    echo "Could not determine container IP for ${CONTAINER_NAME}" >&2
    return 1
  fi

  stop_forwarder "${port}"
  write_forwarder "${port}"

  local fscript fpid flog
  fscript="$(forward_script_file "${port}")"
  fpid="$(forward_pid_file "${port}")"
  flog="$(forward_log_file "${port}")"

  nohup python3 "${fscript}" "${ip}" "${port}" "0.0.0.0" "${port}" > "${flog}" 2>&1 &
  echo "$!" > "${fpid}"
  sleep 1

  if ! kill -0 "$(cat "${fpid}")" 2>/dev/null; then
    echo "Forwarder ${port} failed to start. Log:" >&2
    cat "${flog}" >&2 || true
    return 1
  fi
  echo "Forwarder :${port} -> ${ip}:${port} started"
}

stop_all_forwarders() {
  stop_forwarder "${HTTP_PORT}"
  stop_forwarder "${WS_PORT}"
}

# ── Server management ─────────────────────────────────────────

stop_server() {
  docker exec "${CONTAINER_NAME}" bash -lc \
    "pkill -f 'collect_data_web.py' 2>/dev/null || true" \
    >/dev/null 2>&1 || true
}

start_server() {
  docker start "${CONTAINER_NAME}" >/dev/null

  container_exec "test -f '${WORKSPACE_DIR}/collect_data_web.py'"
  container_exec "mkdir -p '$(dirname "${SERVER_LOG}")'"
  stop_server

  docker exec -d "${CONTAINER_NAME}" bash -lc \
    "cd '${WORKSPACE_DIR}'; : > '${SERVER_LOG}'; /opt/workspace/openpi/.venv/bin/python '${WORKSPACE_DIR}/collect_data_web.py' --http-port='${HTTP_PORT}' --ws-port='${WS_PORT}' --robot-host='${ROBOT_HOST}' --robot-port='${ROBOT_PORT}' >> '${SERVER_LOG}' 2>&1" \
    >/dev/null

  echo "Waiting for WebUI server..."
  for _ in $(seq 1 30); do
    if docker exec "${CONTAINER_NAME}" bash -lc "curl -fsS --max-time 1 http://127.0.0.1:${HTTP_PORT} >/dev/null 2>&1"; then
      echo "WebUI server is ready."
      return 0
    fi
    sleep 1
  done

  echo "WebUI server did not become ready. Last log lines:" >&2
  container_exec "tail -60 '${SERVER_LOG}'" >&2 || true
  return 1
}

# ── Commands ──────────────────────────────────────────────────

cmd_start() {
  start_server
  start_forwarder "${HTTP_PORT}"
  start_forwarder "${WS_PORT}"
  cmd_status
}

cmd_stop() {
  stop_all_forwarders
  stop_server
  echo "Stopped."
}

cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

cmd_status() {
  echo "Container:"
  docker ps --filter "name=^/${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || echo "not running"
  echo ""

  echo "Server process in container:"
  docker exec "${CONTAINER_NAME}" bash -lc \
    "ps -eo pid,stat,etime,rss,cmd | grep collect_data_web | grep -v grep || echo '(not running)'" \
    || echo "(could not check)"
  echo ""

  for port in "${HTTP_PORT}" "${WS_PORT}"; do
    local pid_file fpid
    pid_file="$(forward_pid_file "${port}")"
    if [[ -f "${pid_file}" ]] && fpid="$(cat "${pid_file}")" && kill -0 "${fpid}" 2>/dev/null; then
      echo "Forwarder :${port} running (pid=${fpid})"
    else
      echo "Forwarder :${port} not running"
    fi
  done
  echo ""

  echo "Health check (via host forwarder):"
  curl -fsS --max-time 2 "http://127.0.0.1:${HTTP_PORT}" >/dev/null && echo "  HTTP :${HTTP_PORT} OK" || echo "  HTTP :${HTTP_PORT} FAIL"
  echo ""
}

cmd_logs() {
  echo "=== Server log ==="
  container_exec "tail -100 '${SERVER_LOG}'" 2>/dev/null || echo "(no log)"
  echo ""
  for port in "${HTTP_PORT}" "${WS_PORT}"; do
    local flog
    flog="$(forward_log_file "${port}")"
    if [[ -f "${flog}" ]]; then
      echo "=== Forwarder :${port} log ==="
      tail -20 "${flog}" 2>/dev/null || true
      echo ""
    fi
  done
}

# ── Main ───────────────────────────────────────────────────────

cmd="${1:-start}"
case "${cmd}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    cmd_logs ;;
  -h|--help|help) usage ;;
  *)
    usage >&2
    exit 2
    ;;
esac
