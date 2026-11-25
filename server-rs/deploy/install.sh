#!/usr/bin/env bash
# Cài bypass-server (Rust) lên VPS Ubuntu/Debian có sẵn Chrome + Python engine.
#
#   sudo ./install.sh /opt/link4m
#
# Script chỉ làm 3 việc: copy binary, tạo user, cài systemd unit.
# Nó KHÔNG cài Chrome/Python browser stack — chạy server-rs/Dockerfile nếu
# muốn mọi thứ tự động.

set -euo pipefail

TARGET="${1:-/opt/link4m}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BIN="$HERE/../target/release/bypass-server"

if [[ $EUID -ne 0 ]]; then
    echo "cần root: sudo ./install.sh $TARGET" >&2
    exit 1
fi

if [[ ! -x "$BIN" ]]; then
    echo "chưa có binary release. Chạy trước:" >&2
    echo "  cargo build --release --manifest-path $REPO/server-rs/Cargo.toml" >&2
    exit 1
fi

command -v google-chrome >/dev/null || command -v chromium >/dev/null || {
    echo "thiếu Chrome/Chromium — engine Link4M cần browser thật" >&2
    exit 1
}

id -u l4m >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin l4m

install -d -o l4m -g l4m "$TARGET" "$TARGET/data" "$TARGET/logs"
install -m 0755 "$BIN" /usr/local/bin/bypass-server

# Chỉ copy phần runtime của repo, không copy .git/.venv/target
for item in src service requirements.txt data logs; do
    [[ -e "$REPO/$item" ]] || continue
    cp -a "$REPO/$item" "$TARGET/"
done

if [[ ! -f "$TARGET/server-rs/.env" ]]; then
    install -d "$TARGET/server-rs"
    install -m 0640 -o l4m -g l4m "$HERE/.env.example" "$TARGET/server-rs/.env"
    echo "đã tạo $TARGET/server-rs/.env — sửa API_KEY/PORT trước khi start"
fi

install -m 0644 "$HERE/l4m-bypass-rs.service" /etc/systemd/system/l4m-bypass-rs.service
systemctl daemon-reload
systemctl enable --now l4m-bypass-rs.service

sleep 2
systemctl --no-pager --lines=5 status l4m-bypass-rs.service || true
echo
echo "kiểm tra: curl -s localhost:8080/health"
