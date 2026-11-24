#!/usr/bin/env bash
# Cài service trên server Debian/Ubuntu không GUI (bare metal).
#   sudo bash deploy/install.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"

echo "[*] App dir: $APP_DIR (user: $RUN_USER)"

echo "[*] Cài gói hệ thống..."
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates wget gnupg sox ffmpeg xvfb python3 python3-venv python3-pip \
  libgl1 libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2

if ! command -v google-chrome >/dev/null 2>&1; then
  echo "[*] Cài Google Chrome..."
  wget -q -O /tmp/chrome.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  apt-get install -y --no-install-recommends /tmp/chrome.deb
  rm -f /tmp/chrome.deb
fi

echo "[*] Tạo virtualenv + cài Python deps..."
cd "$APP_DIR"
[ -d .venv ] || sudo -u "$RUN_USER" python3 -m venv .venv
sudo -u "$RUN_USER" .venv/bin/pip install -q --upgrade pip
sudo -u "$RUN_USER" .venv/bin/pip install -q -r service/requirements.txt

echo "[*] Cài systemd unit..."
sed "s|User=koshino|User=$RUN_USER|; s|/home/koshino/Link4M-Bypass-Suite|$APP_DIR|g" \
  deploy/l4m-bypass.service > /etc/systemd/system/l4m-bypass.service
systemctl daemon-reload
systemctl enable --now l4m-bypass

echo
echo "[✓] Xong. Kiểm tra:"
echo "    systemctl status l4m-bypass"
echo "    curl -s http://127.0.0.1:8080/health"
echo "    curl -s 'http://127.0.0.1:8080/api/v1/bypass?url=https://link4m.net/go/2kCcIqn&wait=1'"
