#!/usr/bin/env bash
# Codespaces/devcontainer setup: everything needed to build and run the engine
# inside the sandbox, so the laptop only edits files.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_ROOT"

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl xvfb x11-utils \
  cmake g++ make pkg-config \
  fonts-dejavu-core libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2t64 libpango-1.0-0 libcairo2 libatspi2.0-0

if ! command -v google-chrome >/dev/null 2>&1; then
  sudo install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub |
    sudo tee /etc/apt/keyrings/google-chrome.asc >/dev/null
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] \
https://dl.google.com/linux/chrome/deb/ stable main" |
    sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends google-chrome-stable
fi

python3 -m venv "$REPO_ROOT/.venv"
"$REPO_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_ROOT/.venv/bin/pip" install --quiet \
  rapidocr_onnxruntime opencv-python-headless pillow

mkdir -p "$REPO_ROOT/engine-rs/models"
if [ ! -s "$REPO_ROOT/engine-rs/models/ggml-tiny.en.bin" ]; then
  curl -fL --retry 3 \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin \
    -o "$REPO_ROOT/engine-rs/models/ggml-tiny.en.bin"
fi

cd "$REPO_ROOT/engine-rs"
WHISPER_DONT_GENERATE_BINDINGS=1 cargo build --profile release-fast

echo
echo "sandbox ready."
echo "  test : WHISPER_DONT_GENERATE_BINDINGS=1 PATH=\"$REPO_ROOT/.venv/bin:\$PATH\" cargo test"
echo "  xvfb : Xvfb :99 -screen 0 1280x1000x24 -ac & export DISPLAY=:99"
echo "  run  : L4M_HEADLESS=0 DISPLAY=:99 WORKERS=1 ./target/release-fast/l4m-engine --once <url>"
