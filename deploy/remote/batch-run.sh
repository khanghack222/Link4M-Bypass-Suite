#!/usr/bin/env bash
# Run a list of URLs through a local engine instance and append one JSON line
# per link. Used by the GitHub Actions batch job and usable on any box.
#
#   ./deploy/remote/batch-run.sh links.txt out.jsonl
#
# Env: L4M_DIR (repo root), WORKERS, JOB_TIMEOUT, L4M_API_KEY.
set -euo pipefail

LIST=${1:?usage: batch-run.sh <links.txt> <out.jsonl>}
OUT=${2:?usage: batch-run.sh <links.txt> <out.jsonl>}
L4M_DIR=${L4M_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
WORKERS=${WORKERS:-1}
API_KEY=${L4M_API_KEY:-}
PORT=${PORT:-8080}

# The script changes directory into engine-rs, so both paths are pinned to
# absolute here; relative arguments used to resolve under engine-rs/ and the
# workflow failed with "data/batch.txt: No such file or directory".
LIST=$(realpath "$LIST")
OUT=$(realpath -m "$OUT")
mkdir -p "$(dirname "$OUT")"

cd "$L4M_DIR/engine-rs"
export PATH="$L4M_DIR/.venv/bin:$PATH"

if [ -z "${DISPLAY:-}" ]; then
  Xvfb :99 -screen 0 1280x1000x24 -ac -nolisten tcp &
  XVFB_PID=$!
  export DISPLAY=:99
  trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT
  for _ in $(seq 1 25); do
    [ -S /tmp/.X11-unix/X99 ] && break
    sleep 0.2
  done
fi

L4M_HEADLESS=0 WORKERS="$WORKERS" API_KEY="$API_KEY" \
  ./target/release/l4m-engine >"$L4M_DIR/engine-batch.log" 2>&1 &
ENGINE_PID=$!
trap 'kill "$ENGINE_PID" 2>/dev/null || true; kill "${XVFB_PID:-}" 2>/dev/null || true' EXIT

ready=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" != "1" ]; then
  echo "engine did not become healthy; log:" >&2
  tail -n 40 "$L4M_DIR/engine-batch.log" >&2
  exit 1
fi

: >"$OUT"
auth=()
[ -n "$API_KEY" ] && auth=(-H "x-api-key:$API_KEY")

while IFS= read -r url; do
  url=$(printf '%s' "$url" | tr -d '\r' | sed 's/^ *//;s/ *$//')
  [ -z "$url" ] && continue
  case "$url" in \#*) continue ;; esac
  body=$(python3 -c 'import json,sys;print(json.dumps({"url":sys.argv[1],"wait":True}))' "$url")
  started=$(date +%s)
  result=$(curl -sS --max-time 600 -X POST \
    "${auth[@]}" -H 'content-type: application/json' -d "$body" \
    "http://127.0.0.1:$PORT/api/v1/bypass" || printf '{"status":"error"}')
  took=$(( $(date +%s) - started ))
  python3 - "$url" "$result" "$took" >>"$OUT" <<'PY'
import json, sys
url, raw, took = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    result = json.loads(raw)
except Exception:
    result = {"status": "error", "raw": raw[:200]}
print(json.dumps({"url": url, "took_s": took, **result}, ensure_ascii=False))
PY
  printf '%s -> %s (%ss)\n' "$url" "$(printf '%s' "$result" | head -c 160)" "$took"
done <"$LIST"

kill "$ENGINE_PID" 2>/dev/null || true
wait "$ENGINE_PID" 2>/dev/null || true
echo "results: $OUT"
