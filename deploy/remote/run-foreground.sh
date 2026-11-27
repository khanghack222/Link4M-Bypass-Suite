#!/usr/bin/env bash
# Foreground runner for sandboxes without systemd (GitHub Codespaces, plain
# containers). Starts Xvfb when there is no display, loads /etc/l4m-engine.env
# when present, then execs the engine.
#
#   L4M_DIR=/opt/l4m-engine ./run-foreground.sh
set -euo pipefail

L4M_DIR=${L4M_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
cd "$L4M_DIR/engine-rs"

if [ -f /etc/l4m-engine.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /etc/l4m-engine.env
  set +a
fi

export PATH="$L4M_DIR/.venv/bin:$PATH"

if [ -z "${DISPLAY:-}" ]; then
  if ! command -v Xvfb >/dev/null 2>&1; then
    echo "Xvfb missing; install xvfb or provide DISPLAY" >&2
    exit 1
  fi
  Xvfb :99 -screen 0 1280x1000x24 -ac -nolisten tcp &
  XVFB_PID=$!
  export DISPLAY=:99
  trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT
  # Xvfb opens its socket a beat after the process starts.
  for _ in $(seq 1 20); do
    [ -S /tmp/.X11-unix/X99 ] && break
    sleep 0.2
  done
fi

export L4M_HEADLESS=${L4M_HEADLESS:-0}
export WORKERS=${WORKERS:-1}

exec ./target/release/l4m-engine "$@"
