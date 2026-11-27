#!/usr/bin/env bash
# Thin client: keep the laptop cold, run the browser on a remote engine.
#
#   # SSH mode (VPS / Codespace with SSH)
#   export L4M_REMOTE=user@vps
#   # HTTP mode (Hugging Face Space / any public engine)
#   export L4M_REMOTE=https://user-space.hf.space L4M_API_KEY=...
#
#   ./scripts/remote-l4m.sh health
#   ./scripts/remote-l4m.sh solve https://link4m.net/go/2kCcIqn
#   ./scripts/remote-l4m.sh once  https://link4m.net/go/2kCcIqn   # SSH only
#   ./scripts/remote-l4m.sh batch links.txt
#   ./scripts/remote-l4m.sh logs                                  # SSH only
#   ./scripts/remote-l4m.sh shell                                 # SSH only
#
# Env:
#   L4M_REMOTE      ssh target or http(s) base URL (required)
#   L4M_REMOTE_DIR  repo path on the remote (default /opt/l4m-engine)
#   L4M_API_KEY     x-api-key header when the remote sets API_KEY
#   L4M_PORT        remote engine port in SSH mode (default 8080)
set -euo pipefail

REMOTE=${L4M_REMOTE:?set L4M_REMOTE=user@host or https://host}
REMOTE_DIR=${L4M_REMOTE_DIR:-/opt/l4m-engine}
PORT=${L4M_PORT:-8080}
KEY=${L4M_API_KEY:-}

case "$REMOTE" in
  http://*|https://*) MODE=http; BASE=${REMOTE%/} ;;
  *) MODE=ssh; BASE=http://127.0.0.1:$PORT ;;
esac

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

auth_args() {
  [ -n "$KEY" ] && printf '%s' "-H x-api-key:$KEY"
}

# Run a shell command on the remote (SSH mode only).
remote() {
  [ "$MODE" = ssh ] || { echo "this command needs SSH mode" >&2; exit 1; }
  ssh -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE" "$@"
}

http_get() {
  local path=$1
  if [ "$MODE" = http ]; then
    # shellcheck disable=SC2046
    curl -fsS --max-time 60 $(auth_args) "$BASE$path"
  else
    remote "curl -fsS --max-time 60 $(auth_args) '$BASE$path'"
  fi
}

http_post() {
  local path=$1 body=$2
  if [ "$MODE" = http ]; then
    # shellcheck disable=SC2046
    curl -fsS --max-time 900 -X POST $(auth_args) \
      -H 'content-type: application/json' -d "$body" "$BASE$path"
  else
    remote "curl -fsS --max-time 900 -X POST $(auth_args) \
      -H 'content-type: application/json' -d '$body' '$BASE$path'"
  fi
}

case ${1:-} in
  health)
    http_get /health
    ;;
  solve)
    [ $# -ge 2 ] || usage
    url=$2
    wait=${3:-1}
    body=$(printf '{"url":%s,"wait":%s}' \
      "$(printf '%s' "$url" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
      "$wait")
    http_post /api/v1/bypass "$body"
    ;;
  once)
    [ $# -ge 2 ] || usage
    remote "cd $REMOTE_DIR/engine-rs && L4M_HEADLESS=0 DISPLAY=:99 \
      ./target/release/l4m-engine --once '$2'"
    ;;
  batch)
    [ $# -ge 2 ] || usage
    file=$2
    [ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
    while IFS= read -r url; do
      url=$(printf '%s' "$url" | tr -d '\r' | sed 's/^ *//;s/ *$//')
      [ -z "$url" ] && continue
      case "$url" in \#*) continue ;; esac
      printf '%s\n' "$url"
      "$0" solve "$url" 1 || true
      printf '\n'
    done <"$file"
    ;;
  logs)
    remote "journalctl -u l4m-engine -n 80 --no-pager" 2>/dev/null ||
      remote "tail -n 80 $REMOTE_DIR/engine-rs/engine.log"
    ;;
  shell)
    remote "cd $REMOTE_DIR/engine-rs && exec \$SHELL -l"
    ;;
  *)
    usage
    ;;
esac
