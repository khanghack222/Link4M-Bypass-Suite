#!/usr/bin/env bash
# Quản lý service vượt link: ./deploy/run.sh {start|stop|restart|status|log}
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$APP_DIR/.venv/bin/python"
PIDFILE="$APP_DIR/data/service.pid"
OUT="$APP_DIR/logs/service.out"
PORT="${PORT:-8080}"

mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

_alive() {
  [ -f "$PIDFILE" ] || return 1
  local p; p="$(cat "$PIDFILE" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null
}

start() {
  if _alive; then echo "[=] đã chạy (pid $(cat "$PIDFILE"))"; return 0; fi
  cd "$APP_DIR"
  setsid nohup "$PY" -m service >> "$OUT" 2>&1 < /dev/null &
  echo $! > "$PIDFILE"
  for i in $(seq 1 45); do
    curl -s -m 2 "http://127.0.0.1:$PORT/health" >/dev/null && { echo "[✓] lên sau ${i}s (pid $(cat "$PIDFILE"))"; return 0; }
    sleep 1
  done
  echo "[!] không thấy /health sau 45s — xem $OUT"; return 1
}

stop() {
  _alive || { echo "[=] không chạy"; return 0; }
  local p; p="$(cat "$PIDFILE")"
  kill "$p" 2>/dev/null
  for i in $(seq 1 20); do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
  kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null
  rm -f "$PIDFILE"
  echo "[✓] đã dừng"
}

case "${1:-status}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; start ;;
  status)
    if _alive; then echo "[✓] chạy (pid $(cat "$PIDFILE"))"; curl -s -m 3 "http://127.0.0.1:$PORT/health"; echo
    else echo "[x] không chạy"; fi ;;
  log) tail -n 40 "$OUT" ;;
  *) echo "dùng: $0 {start|stop|restart|status|log}"; exit 2 ;;
esac
