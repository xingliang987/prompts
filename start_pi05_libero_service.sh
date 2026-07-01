#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-pi_dev}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace/openpi}"
CONFIG_NAME="${CONFIG_NAME:-pi05_libero}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/workspace/pi05_libero}"
CONTAINER_PORT="${CONTAINER_PORT:-8000}"
HOST_PORT="${HOST_PORT:-8000}"
HOST_BIND="${HOST_BIND:-0.0.0.0}"
SERVER_LOG="${SERVER_LOG:-${WORKSPACE_DIR}/logs/pi_policy_server_float32.log}"
SERVER_SCRIPT="${SERVER_SCRIPT:-${WORKSPACE_DIR}/scripts/serve_policy_float32.py}"
FORWARD_PID_FILE="${FORWARD_PID_FILE:-/tmp/pi_dev_${HOST_PORT}_forward.pid}"
FORWARD_SCRIPT="${FORWARD_SCRIPT:-/tmp/pi_dev_${HOST_PORT}_forward.py}"
FORWARD_LOG="${FORWARD_LOG:-/tmp/pi_dev_${HOST_PORT}_forward.log}"

usage() {
  cat <<USAGE
Usage: $0 [start|stop|restart|status|logs]

Starts the pi0.5 LIBERO float32 policy server inside Docker and forwards
host ${HOST_BIND}:${HOST_PORT} to the container's ${CONTAINER_PORT}.

Environment overrides:
  CONTAINER_NAME=${CONTAINER_NAME}
  CONFIG_NAME=${CONFIG_NAME}
  CHECKPOINT_DIR=${CHECKPOINT_DIR}
  HOST_PORT=${HOST_PORT}
  CONTAINER_PORT=${CONTAINER_PORT}
USAGE
}

container_exec() {
  docker exec "${CONTAINER_NAME}" bash -lc "$*"
}

container_ip() {
  docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CONTAINER_NAME}"
}

stop_forwarder() {
  if [[ -f "${FORWARD_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${FORWARD_PID_FILE}" || true)"
    if [[ -n "${pid}" ]]; then
      kill "${pid}" 2>/dev/null || true
      sleep 1
      kill -KILL "${pid}" 2>/dev/null || true
    fi
    rm -f "${FORWARD_PID_FILE}"
  fi
}

stop_server() {
  docker exec "${CONTAINER_NAME}" bash -lc \
    "pkill -f 'scripts/serve_policy_float32.py' 2>/dev/null || true; pkill -f '/tmp/serve_policy_f32.py' 2>/dev/null || true" \
    >/dev/null 2>&1 || true
}

stop_all() {
  stop_forwarder
  stop_server
}

write_forwarder() {
  cat > "${FORWARD_SCRIPT}" <<'PY'
import select
import socket
import sys
import threading

target_host = sys.argv[1]
target_port = int(sys.argv[2])
listen_host = sys.argv[3]
listen_port = int(sys.argv[4])


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

start_server() {
  docker start "${CONTAINER_NAME}" >/dev/null

  container_exec "test -f '${SERVER_SCRIPT}'"
  container_exec "test -d '${CHECKPOINT_DIR}/params'"
  container_exec "mkdir -p '$(dirname "${SERVER_LOG}")'"
  stop_server

  docker exec -d "${CONTAINER_NAME}" bash -lc \
    "cd '${WORKSPACE_DIR}'; : > '${SERVER_LOG}'; env XLA_PYTHON_CLIENT_PREALLOCATE=false .venv/bin/python '${SERVER_SCRIPT}' --config='${CONFIG_NAME}' --checkpoint-dir='${CHECKPOINT_DIR}' --port='${CONTAINER_PORT}' >> '${SERVER_LOG}' 2>&1" \
    >/dev/null

  echo "Waiting for policy server health check..."
  for _ in $(seq 1 180); do
    if docker exec "${CONTAINER_NAME}" bash -lc "curl -fsS --max-time 1 http://127.0.0.1:${CONTAINER_PORT}/healthz >/dev/null 2>&1"; then
      echo "Policy server is ready."
      return 0
    fi
    sleep 2
  done

  echo "Policy server did not become ready. Last log lines:" >&2
  docker exec "${CONTAINER_NAME}" bash -lc "tail -160 '${SERVER_LOG}'" >&2 || true
  return 1
}

start_forwarder() {
  local ip
  ip="$(container_ip)"
  if [[ -z "${ip}" ]]; then
    echo "Could not determine container IP for ${CONTAINER_NAME}" >&2
    return 1
  fi

  stop_forwarder
  write_forwarder
  nohup python3 "${FORWARD_SCRIPT}" "${ip}" "${CONTAINER_PORT}" "${HOST_BIND}" "${HOST_PORT}" > "${FORWARD_LOG}" 2>&1 &
  echo "$!" > "${FORWARD_PID_FILE}"
  sleep 1

  if ! kill -0 "$(cat "${FORWARD_PID_FILE}")" 2>/dev/null; then
    echo "Forwarder failed to start. Log:" >&2
    cat "${FORWARD_LOG}" >&2 || true
    return 1
  fi

  echo "Forwarder started: ${HOST_BIND}:${HOST_PORT} -> ${ip}:${CONTAINER_PORT}"
  curl -fsS --max-time 3 "http://127.0.0.1:${HOST_PORT}/healthz" >/dev/null
  echo "Host health check OK: http://127.0.0.1:${HOST_PORT}/healthz"
}

status() {
  echo "Container:"
  docker ps --filter "name=^/${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo
  echo "Policy server process:"
  docker exec "${CONTAINER_NAME}" bash -lc "ps -eo pid,ppid,stat,etime,rss,cmd | grep -E 'serve_policy_float32' | grep -v grep || true" || true
  echo
  echo "Forwarder:"
  if [[ -f "${FORWARD_PID_FILE}" ]] && kill -0 "$(cat "${FORWARD_PID_FILE}")" 2>/dev/null; then
    echo "running pid=$(cat "${FORWARD_PID_FILE}")"
  else
    echo "not running"
  fi
  echo
  echo "Health checks:"
  docker exec "${CONTAINER_NAME}" bash -lc "curl -fsS --max-time 2 http://127.0.0.1:${CONTAINER_PORT}/healthz" || true
  echo
  curl -fsS --max-time 2 "http://127.0.0.1:${HOST_PORT}/healthz" || true
  echo
}

logs() {
  echo "Policy server log: ${SERVER_LOG}"
  docker exec "${CONTAINER_NAME}" bash -lc "tail -200 '${SERVER_LOG}'" || true
  echo
  echo "Forwarder log: ${FORWARD_LOG}"
  tail -80 "${FORWARD_LOG}" 2>/dev/null || true
}

cmd="${1:-start}"
case "${cmd}" in
  start)
    start_server
    start_forwarder
    status
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_server
    start_forwarder
    status
    ;;
  status)
    status
    ;;
  logs)
    logs
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
