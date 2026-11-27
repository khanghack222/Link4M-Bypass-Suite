#!/usr/bin/env bash
# Thin client: keep the laptop cold, run the browser on the remote engine.
#
#   export L4M_REMOTE=user@vps
#   ./scripts/remote-l4m.sh health
#   ./scripts/remote-l4m.sh solve https://link4m.net/go/2kCcIqn
#   ./scripts/remote-l4m.sh once  https://link4m.net/go/2kCcIqn
#   ./scripts/remote-l4m.sh batch links.txt
#   ./scripts/remote-l4m.sh logs
#   ./scripts/remote-l4m.sh shell
#
# Env:
#   L4M_REMOTE      ssh target (required)
#   L4M_REMOTE_DIR  repo path on the remote (default /opt/l4m-engine)
#   L4M_API_KEY     forwarded as ?key= when the remote sets API_KEY
#   L4M_PORT        remote engine port (default 8080)
set -euo pipefail

REMOTE=${L4M_REMOTE:?set L4M_REMOTE=user@host}
REMOTE_DIR=${L4M_REMOTE_DIR:-/opt/l4m-engine}
PORT=${L4M_PORT:-8080}
KEY=${L4M_API_KEY:-}

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

remote() {
  ssh -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE" "$@"
}

query() {
  if [ -n "$KEY" ]; then
    printf '%s?key=%s' "$1" "$KEY"
  else
    printf '%s' "$1"
  fi
}

auth_header() {
  if [ -n "$KEY" ]; then
    printf -- '-H x-api-key:%s' "$KEY"
  fi
}

case ${1:-} in
  health)
    remote "curl -fsS http://127.0.0.1:$PORT/health"
    ;;
  solve)
    [ $# -ge 2 ] || usage
    url=$2
    wait=${3:-1}
    body=$(printf '{"url":%s,"wait":%s}' \
      "$(printf '%s' "$url" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
      "$wait")
    remote "curl -fsS -X POST http://127.0.0.1:$PORT/api/v1/bypass \
      -H 'content-type: application/json' $(auth_header) -d '$body'"
    ;;
  once)
    [ $# -ge 2 ] || usage
    url=$2
    remote "cd $REMOTE_DIR/engine-rs && L4M_HEADLESS=0 DISPLAY=:99 \
      ./target/release/l4m-engine --once '$url'"
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
