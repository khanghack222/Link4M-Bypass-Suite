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
# A batch answer served from the cache says nothing about the egress IP, and a
# cached success after a proxy swap hid a dead relay once. Solve for real.
FRESH=${L4M_FRESH:-1}

# The script changes directory into engine-rs, so both paths are pinned to
# absolute here; relative arguments used to resolve under engine-rs/ and the
# workflow failed with "data/batch.txt: No such file or directory".
LIST=$(realpath "$LIST")
OUT=$(realpath -m "$OUT")
mkdir -p "$(dirname "$OUT")"

cd "$L4M_DIR/engine-rs"
export PATH="$L4M_DIR/.venv/bin:$PATH"

XVFB=$(command -v Xvfb || true)
if [ -z "${DISPLAY:-}" ] && [ -n "$XVFB" ]; then
  "$XVFB" :99 -screen 0 1280x1000x24 -ac -nolisten tcp &
  XVFB_PID=$!
  export DISPLAY=:99
  trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT
  for _ in $(seq 1 25); do
    [ -S /tmp/.X11-unix/X99 ] && break
    sleep 0.2
  done
fi

# A windowed Chrome with no X server never finishes booting and never writes
# DevToolsActivePort, so every job burned its 30 s CDP window instead of
# failing fast. No display means headless; an explicit L4M_HEADLESS still wins.
if [ -n "${L4M_HEADLESS:-}" ]; then
  HEADLESS=$L4M_HEADLESS
elif [ -n "${DISPLAY:-}" ]; then
  HEADLESS=0
else
  HEADLESS=1
fi

# PROXY_LIST may be unset; `env` keeps the assignment a real assignment. A
# ${VAR:+VAR=...} word on the command line gets expanded after bash has already
# decided which words are assignments, so it ran as a command name instead.
[ -n "${PROXY_LIST:-}" ] && export PROXY_LIST
ENGINE_BIN="./target/release-fast/l4m-engine"
[ ! -x "$ENGINE_BIN" ] && ENGINE_BIN="./target/release/l4m-engine"
env L4M_HEADLESS="$HEADLESS" WORKERS="$WORKERS" API_KEY="$API_KEY" \
  "$ENGINE_BIN" >"$L4M_DIR/engine-batch.log" 2>&1 &
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
  body=$(python3 -c 'import json,sys;fresh=sys.argv[2] not in ("0","false","no","");print(json.dumps({"url":sys.argv[1],"wait":True,"fresh":fresh}))' "$url" "$FRESH")
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
