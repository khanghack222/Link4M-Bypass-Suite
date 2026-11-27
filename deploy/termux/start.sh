#!/usr/bin/env bash
# Self-host the engine on an Android phone: Termux -> proot Debian -> here.
#
#   pkg install proot-distro
#   proot-distro install debian
#   proot-distro login debian
#   apt-get update && apt-get install -y curl git
#   curl -fsSL https://raw.githubusercontent.com/<owner>/Link4M-Bypass-Suite/main/deploy/termux/start.sh | bash
#
# Phone must stay plugged in: Chrome + whisper keep the CPU warm.
# Env: L4M_RELEASE=latest, L4M_DIR=/opt/l4m-engine, API_KEY, TUNNEL=1.
set -euo pipefail

L4M_RELEASE=${L4M_RELEASE:-latest}
L4M_DIR=${L4M_DIR:-/opt/l4m-engine}
REPO_SLUG=${REPO_SLUG:-khanghack222/Link4M-Bypass-Suite}
TUNNEL=${TUNNEL:-1}

if [ "$(id -u)" -ne 0 ]; then
  echo "run inside proot as root" >&2
  exit 1
fi

ARCH=$(uname -m)
case "$ARCH" in
  aarch64|arm64) ASSET=l4m-engine-linux-arm64.tar.gz ;;
  x86_64|amd64) ASSET=l4m-engine-linux-x86_64.tar.gz ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl xvfb x11-utils \
  chromium python3 python3-venv python3-pip \
  fonts-dejavu-core libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2 libpango-1.0-0 libcairo2 libatspi2.0-0

if [ "$L4M_RELEASE" = "latest" ]; then
  ASSET_URL="https://github.com/$REPO_SLUG/releases/latest/download/$ASSET"
else
  ASSET_URL="https://github.com/$REPO_SLUG/releases/download/$L4M_RELEASE/$ASSET"
fi

mkdir -p "$L4M_DIR"
curl -fL --retry 3 "$ASSET_URL" -o /tmp/l4m.tar.gz
tar -C "$L4M_DIR" -xzf /tmp/l4m.tar.gz
mkdir -p "$L4M_DIR/engine-rs/target/release"
cp "$L4M_DIR/l4m-engine" "$L4M_DIR/engine-rs/target/release/l4m-engine"
cp -r "$L4M_DIR/tools" "$L4M_DIR/engine-rs/tools"
cp -r "$L4M_DIR/models" "$L4M_DIR/engine-rs/models"

python3 -m venv "$L4M_DIR/.venv"
"$L4M_DIR/.venv/bin/pip" install -q --upgrade pip
"$L4M_DIR/.venv/bin/pip" install -q rapidocr_onnxruntime opencv-python-headless pillow

export DISPLAY=:99
Xvfb :99 -screen 0 1280x1000x24 -ac -nolisten tcp >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 25); do [ -S /tmp/.X11-unix/X99 ] && break; sleep 0.2; done

API_KEY=${API_KEY:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}
export L4M_DIR HOST=0.0.0.0 PORT=8080 API_KEY
export L4M_HEADLESS=0 WORKERS=1 L4M_PREWARM=1 L4M_OCR_SERVE=1
export CHROME_BIN=${CHROME_BIN:-/usr/bin/chromium}

if [ "$TUNNEL" = "1" ]; then
  if ! command -v cloudflared >/dev/null 2>&1; then
    case "$ARCH" in
      aarch64|arm64) CF=cloudflared-linux-arm64 ;;
      *) CF=cloudflared-linux-amd64 ;;
    esac
    curl -fsSL --retry 3 \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF" \
      -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
  fi
  nohup cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate \
    >/tmp/cloudflared.log 2>&1 &
  for _ in $(seq 1 60); do
    PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1 || true)
    [ -n "$PUBLIC_URL" ] && break
    sleep 1
  done
  echo "public  : ${PUBLIC_URL:-<tunnel failed>}"
fi

echo "api key : $API_KEY"
echo "engine  : http://<phone-ip>:8080"
nohup "$L4M_DIR/run-foreground.sh" >/tmp/l4m-engine.log 2>&1 &
for _ in $(seq 1 90); do
  curl -fsS --max-time 2 http://127.0.0.1:8080/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:8080/health || {
  echo "engine failed, log:" >&2
  tail -n 40 /tmp/l4m-engine.log >&2
  exit 1
}
echo "keep the proot session open; logs /tmp/l4m-engine.log"
exec tail -f /tmp/l4m-engine.log
