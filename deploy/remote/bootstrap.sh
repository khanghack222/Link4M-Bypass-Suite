#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu box (VPS, Codespace, cloud sandbox) as a Link4M
# engine host. Installs Chrome + Xvfb + Rust + RapidOCR, builds the engine and
# wires systemd so the browser stays off the laptop.
#
#   sudo REPO_URL=https://github.com/you/Link4M-Bypass-Suite.git ./bootstrap.sh
#
# Options (env):
#   L4M_DIR      install root              (default /opt/l4m-engine)
#   L4M_USER     service user              (default l4m)
#   REPO_URL     git remote to clone       (default: this checkout's origin)
#   L4M_BRANCH   branch                    (default main)
#   SKIP_BUILD=1 clone + configure only
set -euo pipefail

L4M_DIR=${L4M_DIR:-/opt/l4m-engine}
L4M_USER=${L4M_USER:-l4m}
L4M_BRANCH=${L4M_BRANCH:-main}
SKIP_BUILD=${SKIP_BUILD:-0}

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root (sudo)" >&2
  exit 1
fi

if [ -z "${REPO_URL:-}" ]; then
  REPO_URL=$(git -C "$(dirname "$0")/../.." remote get-url origin 2>/dev/null || true)
fi
if [ -z "${REPO_URL:-}" ]; then
  echo "REPO_URL is required" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git unzip xz-utils \
  xvfb x11-utils \
  cmake g++ make pkg-config \
  python3 python3-venv python3-pip \
  fonts-dejavu-core libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2t64 libpango-1.0-0 libcairo2 libatspi2.0-0

# Chrome: Google's apt repo, not the snap stub Ubuntu ships.
if ! command -v google-chrome >/dev/null 2>&1; then
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    -o /etc/apt/keyrings/google-chrome.asc
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] \
https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update
  apt-get install -y --no-install-recommends google-chrome-stable
fi

if ! id "$L4M_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$L4M_USER"
fi

if [ ! -d "$L4M_DIR/.git" ]; then
  git clone --branch "$L4M_BRANCH" "$REPO_URL" "$L4M_DIR"
else
  git -C "$L4M_DIR" fetch origin "$L4M_BRANCH"
  git -C "$L4M_DIR" checkout "$L4M_BRANCH"
  git -C "$L4M_DIR" pull --ff-only origin "$L4M_BRANCH"
fi
chown -R "$L4M_USER:$L4M_USER" "$L4M_DIR"

# Rust for the service user. rustup installs into the user's home, so the
# build and the systemd unit agree on the toolchain path.
if ! sudo -u "$L4M_USER" bash -lc 'command -v cargo' >/dev/null 2>&1; then
  sudo -u "$L4M_USER" bash -lc \
    'curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal'
fi

if [ ! -x "$L4M_DIR/.venv/bin/python" ]; then
  sudo -u "$L4M_USER" python3 -m venv "$L4M_DIR/.venv"
fi
sudo -u "$L4M_USER" "$L4M_DIR/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$L4M_USER" "$L4M_DIR/.venv/bin/pip" install --quiet \
  rapidocr_onnxruntime opencv-python-headless pillow

if [ ! -s "$L4M_DIR/engine-rs/models/ggml-tiny.en.bin" ]; then
  mkdir -p "$L4M_DIR/engine-rs/models"
  sudo -u "$L4M_USER" curl -fL --retry 3 \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin \
    -o "$L4M_DIR/engine-rs/models/ggml-tiny.en.bin"
fi

if [ "$SKIP_BUILD" != "1" ]; then
  sudo -u "$L4M_USER" bash -lc "
    cd '$L4M_DIR/engine-rs'
    export PATH=\"\$HOME/.cargo/bin:\$PATH\"
    export WHISPER_DONT_GENERATE_BINDINGS=1
    export PATH='$L4M_DIR/.venv/bin:'\$PATH
    cargo build --release
  "
fi

if [ ! -f /etc/l4m-engine.env ]; then
  cat > /etc/l4m-engine.env <<'EOF'
# Link4M engine service environment. Keep HOST on loopback and reach the API
# through an SSH tunnel; only put a public bind behind API_KEY + a proxy.
HOST=127.0.0.1
PORT=8080
API_KEY=
WORKERS=1
L4M_HEADLESS=0
L4M_PREWARM=1
L4M_OCR_SERVE=1
WHISPER_MODEL=models/ggml-tiny.en.bin
EOF
  chmod 600 /etc/l4m-engine.env
fi

install -d -m 0755 /etc/systemd/system
cat > /etc/systemd/system/l4m-xvfb.service <<'EOF'
[Unit]
Description=Xvfb display for l4m-engine
After=network.target

[Service]
ExecStart=/usr/bin/Xvfb :99 -screen 0 1280x1000x24 -ac -nolisten tcp
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/l4m-engine.service <<EOF
[Unit]
Description=Link4M bypass engine
After=network.target l4m-xvfb.service
Requires=l4m-xvfb.service

[Service]
Type=simple
User=$L4M_USER
WorkingDirectory=$L4M_DIR/engine-rs
EnvironmentFile=/etc/l4m-engine.env
Environment=DISPLAY=:99
Environment=PATH=$L4M_DIR/.venv/bin:/home/$L4M_USER/.cargo/bin:/usr/local/bin:/usr/bin:/bin
Environment=RUST_LOG=engine=info
ExecStart=$L4M_DIR/engine-rs/target/release/l4m-engine
Restart=always
RestartSec=3
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now l4m-xvfb.service
systemctl enable --now l4m-engine.service

sleep 3
systemctl --no-pager --lines=5 status l4m-engine.service || true
echo
echo "engine: $(curl -fsS http://127.0.0.1:8080/health || echo 'health check failed')"
echo "logs:   journalctl -u l4m-engine -f"
