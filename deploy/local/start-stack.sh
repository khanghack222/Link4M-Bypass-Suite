#!/usr/bin/env bash
# ==============================================================================
# Link4M Bypass Suite - Local Stack Launcher (Low-RAM Durable Edition)
# Runs native Rust CDP engine + Discord Bot with preflight checks and clean traps.
# Tailored for low-RAM Linux environments (3.7 GB RAM host).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Ensure data and log directories exist
mkdir -p "$REPO_ROOT/data" "$REPO_ROOT/logs"

# Load environment configuration if available
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

# ------------------------------------------------------------------------------
# Default Low-RAM Settings & Defaults (Guaranteed safe for 3.7GB RAM)
# ------------------------------------------------------------------------------
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-1}"                    # 1 worker = strictly 1 Chrome instance (safe for 3.7GB RAM)
L4M_PREWARM="${L4M_PREWARM:-0}"            # 0 = lazy launch Chrome on demand to save memory
L4M_JOB_RETRIES="${L4M_JOB_RETRIES:-3}"    # 3x auto-retry on audio/IP rate limit
L4M_SPOOF_WARP="${L4M_SPOOF_WARP:-1}"      # Spoof Cloudflare WARP client headers on Link4M requests
PROXY_ROTATE="${PROXY_ROTATE:-1}"          # Rotate proxy exit after each job
PROXY_FILE="${PROXY_FILE:-$REPO_ROOT/proxies.txt}"
RUST_LOG="${RUST_LOG:-l4m_engine=info,engine=info}"
L4M_ENGINE_URL="${L4M_ENGINE_URL:-http://$HOST:$PORT}"
export HOST PORT WORKERS L4M_PREWARM L4M_JOB_RETRIES L4M_SPOOF_WARP PROXY_ROTATE PROXY_FILE RUST_LOG L4M_ENGINE_URL

echo "======================================================================"
echo " Starting Link4M Local Stack (Low-RAM Linux 3.7GB)"
echo " Engine URL:     $L4M_ENGINE_URL"
echo " Workers:        $WORKERS (L4M_PREWARM=$L4M_PREWARM)"
echo " Retries:        $L4M_JOB_RETRIES attempts"
echo " Proxy Pool:     $PROXY_FILE (rotate=$PROXY_ROTATE)"
echo "======================================================================"

# ------------------------------------------------------------------------------
# Preflight Check 1: Google Chrome / Chromium
# ------------------------------------------------------------------------------
find_chrome() {
  if [ -n "${CHROME_BIN:-}" ] && [ -x "$CHROME_BIN" ]; then
    echo "$CHROME_BIN"
    return 0
  fi
  for bin in \
    /usr/bin/google-chrome \
    /usr/bin/google-chrome-stable \
    /usr/bin/chromium \
    /usr/bin/chromium-browser \
    "$(command -v google-chrome 2>/dev/null || true)" \
    "$(command -v google-chrome-stable 2>/dev/null || true)" \
    "$(command -v chromium 2>/dev/null || true)"
  do
    if [ -n "$bin" ] && [ -x "$bin" ]; then
      echo "$bin"
      return 0
    fi
  done
  return 1
}

CHROME_EXEC="$(find_chrome || true)"
if [ -z "$CHROME_EXEC" ]; then
  echo "[!] ERROR: Chrome / Chromium binary not found!" >&2
  echo "    Install via: sudo apt-get install -y google-chrome-stable (or chromium)" >&2
  echo "    Or specify CHROME_BIN=/path/to/chrome in .env" >&2
  exit 1
fi
export CHROME_BIN="$CHROME_EXEC"
echo "[✓] Chrome binary: $CHROME_BIN"

# Headless / Display configuration (Strict Headless by default)
if [ -z "${L4M_HEADLESS:-}" ]; then
  export L4M_HEADLESS=1
  echo "[i] Defaulting L4M_HEADLESS=1 (strict headless=new mode)."
fi

# ------------------------------------------------------------------------------
# Preflight Check 2: Whisper GGML Model (Audio reCAPTCHA Solver)
# ------------------------------------------------------------------------------
MODEL_PATH="${WHISPER_MODEL:-}"
if [ -z "$MODEL_PATH" ]; then
  if [ -f "$REPO_ROOT/engine-rs/models/ggml-tiny.en.bin" ]; then
    MODEL_PATH="$REPO_ROOT/engine-rs/models/ggml-tiny.en.bin"
  elif [ -f "$REPO_ROOT/models/ggml-tiny.en.bin" ]; then
    MODEL_PATH="$REPO_ROOT/models/ggml-tiny.en.bin"
  else
    MODEL_PATH="$REPO_ROOT/engine-rs/models/ggml-tiny.en.bin"
  fi
fi

if [ ! -f "$MODEL_PATH" ]; then
  echo "[i] Whisper model not found at $MODEL_PATH. Downloading ggml-tiny.en.bin (~75MB)..."
  mkdir -p "$(dirname "$MODEL_PATH")"
  curl -fL --retry 3 \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin" \
    -o "$MODEL_PATH"
  echo "[✓] Downloaded whisper model to $MODEL_PATH"
fi
export WHISPER_MODEL="$MODEL_PATH"
echo "[✓] Whisper model: $WHISPER_MODEL"

# ------------------------------------------------------------------------------
# Preflight Check 3: l4m-engine Rust Binary
# ------------------------------------------------------------------------------
find_engine_bin() {
  for bin in \
    "$REPO_ROOT/engine-rs/target/release-fast/l4m-engine" \
    "$REPO_ROOT/engine-rs/target/release/l4m-engine" \
    "$REPO_ROOT/bin/l4m-engine" \
    "$REPO_ROOT/l4m-engine" \
    "$(command -v l4m-engine 2>/dev/null || true)"
  do
    if [ -n "$bin" ] && [ -x "$bin" ]; then
      echo "$bin"
      return 0
    fi
  done
  return 1
}

ENGINE_BIN="$(find_engine_bin || true)"
if [ -z "$ENGINE_BIN" ]; then
  echo "[i] l4m-engine binary not found. Attempting to build with cargo..."
  if command -v cargo >/dev/null 2>&1; then
    cargo build --profile release-fast --manifest-path "$REPO_ROOT/engine-rs/Cargo.toml"
    ENGINE_BIN="$REPO_ROOT/engine-rs/target/release-fast/l4m-engine"
  else
    echo "[!] ERROR: Rust engine binary missing and cargo not installed!" >&2
    echo "    Please build via: cargo build --profile release-fast (in engine-rs/)" >&2
    exit 1
  fi
fi
echo "[✓] Engine binary: $ENGINE_BIN"

# ------------------------------------------------------------------------------
# Preflight Check 4: Node.js & bot_discord.js
# ------------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  echo "[!] ERROR: node executable not found in PATH!" >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/bot_discord.js" ]; then
  echo "[!] ERROR: bot_discord.js not found at $REPO_ROOT/bot_discord.js" >&2
  exit 1
fi

if [ ! -d "$REPO_ROOT/node_modules" ]; then
  echo "[!] Warning: node_modules directory missing. Running npm install..."
  (cd "$REPO_ROOT" && npm install --silent)
fi

# ------------------------------------------------------------------------------
# Cleanup & Signal Trapping (Reaps background jobs & Chrome cleanly)
# ------------------------------------------------------------------------------
ENGINE_PID=""
BOT_PID=""

cleanup() {
  echo ""
  echo "[i] Shutdown signal received. Stopping stack gracefully..."
  trap - INT TERM EXIT HUP

  if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
    echo "[i] Stopping Discord bot (PID $BOT_PID)..."
    kill -TERM "$BOT_PID" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "$BOT_PID" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$BOT_PID" 2>/dev/null || true
  fi

  if [ -n "$ENGINE_PID" ] && kill -0 "$ENGINE_PID" 2>/dev/null; then
    echo "[i] Stopping l4m-engine (PID $ENGINE_PID)..."
    kill -TERM "$ENGINE_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$ENGINE_PID" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$ENGINE_PID" 2>/dev/null || true
  fi

  # Clean any background jobs belonging to this shell
  # shellcheck disable=SC2046
  kill $(jobs -p) 2>/dev/null || true

  # Sweep any orphaned Chrome processes belonging strictly to l4m engine profiles
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "[u]ser-data-dir=.*(l4m-|l4m-profile|l4m-check|chrome_link4m_profile|chrome-profile)" 2>/dev/null || true
  fi

  echo "[✓] Stack stopped cleanly."
}

trap cleanup INT TERM EXIT HUP

# ------------------------------------------------------------------------------
# Step 1: Start l4m-engine Daemon
# ------------------------------------------------------------------------------
ENGINE_LOG="$REPO_ROOT/logs/engine.log"
echo "[i] Launching l4m-engine daemon on $HOST:$PORT..."
"$ENGINE_BIN" > "$ENGINE_LOG" 2>&1 &
ENGINE_PID=$!

echo "[i] Waiting for engine health on http://127.0.0.1:$PORT/health ..."
HEALTHY=0
for i in $(seq 1 45); do
  if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
    echo "[!] ERROR: l4m-engine exited unexpectedly! Check $ENGINE_LOG" >&2
    tail -n 30 "$ENGINE_LOG" >&2
    exit 1
  fi
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    HEALTHY=1
    echo "[✓] l4m-engine is healthy and ready on http://$HOST:$PORT (took ${i}s) [PID: $ENGINE_PID]"
    break
  fi
  sleep 1
done

if [ "$HEALTHY" -ne 1 ]; then
  echo "[!] ERROR: Timed out waiting for l4m-engine health on :$PORT after 45s!" >&2
  tail -n 40 "$ENGINE_LOG" >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# Step 2: Start Discord Bot
# ------------------------------------------------------------------------------
echo "======================================================================"
echo " Starting Discord Bot (Node.js)"
echo " Connecting to Rust Daemon: $L4M_ENGINE_URL"
echo " Press Ctrl+C at any time to stop both Engine and Bot cleanly."
echo "======================================================================"

node "$REPO_ROOT/bot_discord.js" &
BOT_PID=$!

# Wait on bot process (clean trap handles exit)
wait "$BOT_PID"
