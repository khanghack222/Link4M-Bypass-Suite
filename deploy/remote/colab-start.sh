#!/usr/bin/env bash
# One-shot starter for a free notebook VM (Google Colab, Kaggle, SageMaker
# Studio Lab). Installs Chrome + Xvfb, unpacks the published engine tarball,
# runs it and exposes it through a cloudflared quick tunnel.
#
#   !git clone https://github.com/<owner>/Link4M-Bypass-Suite.git /content/l4m
#   !bash /content/l4m/deploy/remote/colab-start.sh
#
# The cell prints the public URL and an API key; keep the cell running. A free
# Colab VM lasts up to ~12 h per session, then rerun the two lines.
#
# Env:
#   L4M_RELEASE  release tag or "latest" (default latest)
#   L4M_DIR      install dir (default /opt/l4m-engine)
set -euo pipefail

L4M_RELEASE=${L4M_RELEASE:-latest}
L4M_DIR=${L4M_DIR:-/opt/l4m-engine}
REPO_SLUG=${REPO_SLUG:-khanghack222/Link4M-Bypass-Suite}

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root (Colab/Kaggle shells are root)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl xvfb x11-utils python3 python3-venv python3-pip \
  fonts-dejavu-core libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2t64 libpango-1.0-0 libcairo2 libatspi2.0-0 >/dev/null

if ! command -v google-chrome >/dev/null 2>&1; then
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    -o /etc/apt/keyrings/google-chrome.asc
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] \
https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends google-chrome-stable >/dev/null
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  curl -fsSL --retry 3 \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi

if [ "$L4M_RELEASE" = "latest" ]; then
  ASSET_URL="https://github.com/$REPO_SLUG/releases/latest/download/l4m-engine-linux-x86_64.tar.gz"
else
  ASSET_URL="https://github.com/$REPO_SLUG/releases/download/$L4M_RELEASE/l4m-engine-linux-x86_64.tar.gz"
fi

mkdir -p "$L4M_DIR"
curl -fL --retry 3 "$ASSET_URL" -o /tmp/l4m-engine.tar.gz
tar -C "$L4M_DIR" -xzf /tmp/l4m-engine.tar.gz
# run-foreground.sh expects <root>/engine-rs/target/release/l4m-engine or release-fast.
mkdir -p "$L4M_DIR/engine-rs/target/release" "$L4M_DIR/engine-rs/target/release-fast"
cp "$L4M_DIR/l4m-engine" "$L4M_DIR/engine-rs/target/release/l4m-engine"
cp "$L4M_DIR/l4m-engine" "$L4M_DIR/engine-rs/target/release-fast/l4m-engine"
cp -r "$L4M_DIR/tools" "$L4M_DIR/engine-rs/tools" 2>/dev/null || true
cp -r "$L4M_DIR/models" "$L4M_DIR/engine-rs/models" 2>/dev/null || true

python3 -m venv "$L4M_DIR/.venv"
"$L4M_DIR/.venv/bin/pip" install -q --upgrade pip
"$L4M_DIR/.venv/bin/pip" install -q rapidocr_onnxruntime opencv-python-headless pillow

export DISPLAY=:99
Xvfb :99 -screen 0 1280x1000x24 -ac -nolisten tcp >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 25); do [ -S /tmp/.X11-unix/X99 ] && break; sleep 0.2; done

API_KEY=${API_KEY:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}
export L4M_DIR HOST=127.0.0.1 PORT=8080 API_KEY
export L4M_HEADLESS=0 WORKERS=1 L4M_PREWARM=1 L4M_OCR_SERVE=1
nohup "$L4M_DIR/run-foreground.sh" >/tmp/l4m-engine.log 2>&1 &
for _ in $(seq 1 90); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/health >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -fsS --max-time 2 http://127.0.0.1:8080/health >/dev/null 2>&1; then
  echo "engine did not start; last log lines:" >&2
  tail -n 40 /tmp/l4m-engine.log >&2
  exit 1
fi

nohup cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate \
  >/tmp/cloudflared.log 2>&1 &
PUBLIC_URL=""
for _ in $(seq 1 60); do
  PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1 || true)
  [ -n "$PUBLIC_URL" ] && break
  sleep 1
done

echo
echo "engine  : http://127.0.0.1:8080"
echo "public  : ${PUBLIC_URL:-<tunnel failed, see /tmp/cloudflared.log>}"
echo "api key : $API_KEY"
echo
if [ -n "$PUBLIC_URL" ]; then
  echo "from the laptop:"
  echo "  export L4M_REMOTE=$PUBLIC_URL L4M_API_KEY=$API_KEY"
  echo "  ./scripts/remote-l4m.sh health"
  echo "  ./scripts/remote-l4m.sh solve https://link4m.net/go/<alias>"
fi
echo
echo "keep this cell running; logs: /tmp/l4m-engine.log"
exec tail -f /tmp/l4m-engine.log
