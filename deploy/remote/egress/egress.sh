#!/usr/bin/env bash
# Publish the home SOCKS5 egress through a public SSH relay.
#
# The remote worker runs Chrome; link4m's Cloudflare edge treats home ISP
# addresses as human and datacenter addresses as bots. This script keeps a
# loopback SOCKS5 listener alive (with credentials) and reconnects a Pinggy TCP
# tunnel whenever the free 60-minute session drops, so the worker's
# PROXY_LIST always points at a live port on the home side.
#
#   ./egress.sh                     # prints the proxy URL, keeps running
#   L4M_EGRESS_VAR=1 ./egress.sh    # also push it to the repo variable
#
# The proxy URL is written to $STATE/proxy.txt after every reconnect.
set -uo pipefail

STATE=${L4M_EGRESS_STATE:-$HOME/.l4m-egress}
KEY=${L4M_EGRESS_KEY:-$STATE/id_ed25519}
PORT=${L4M_EGRESS_PORT:-1081}
RELAY_USER=${L4M_EGRESS_RELAY_USER:-tcp@a.pinggy.io}
RELAY_PORT=${L4M_EGRESS_RELAY_PORT:-443}

mkdir -p "$STATE"
chmod 700 "$STATE"

if [ ! -f "$STATE/password" ]; then
  head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' >"$STATE/password"
  chmod 600 "$STATE/password"
fi
PASSWORD=$(cat "$STATE/password")
USER_NAME=${L4M_EGRESS_USER:-l4m}

if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY" -q
fi

HERE=$(cd "$(dirname "$0")" && pwd)
python3 "$HERE/socks5.py" --port "$PORT" --user "$USER_NAME" --password "$PASSWORD" &
SOCKS_PID=$!
trap 'kill "$SOCKS_PID" 2>/dev/null || true' EXIT
sleep 1
if ! kill -0 "$SOCKS_PID" 2>/dev/null; then
  echo "socks5 failed to start" >&2
  exit 1
fi

publish() {
  local url=$1
  printf '%s\n' "$url" >"$STATE/proxy.txt"
  chmod 600 "$STATE/proxy.txt"
  echo "PROXY_LIST=$url"
  if [ "${L4M_EGRESS_VAR:-0}" = "1" ] && command -v gh >/dev/null 2>&1; then
    gh variable set L4M_EGRESS_PROXY --body "$url" ${L4M_EGRESS_REPO:+--repo "$L4M_EGRESS_REPO"} >/dev/null 2>&1 ||
      echo "could not update repo variable" >&2
  fi
}

while true; do
  LOG=$(mktemp)
  ssh -F /dev/null -p "$RELAY_PORT" -T \
    -i "$KEY" -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes -o PreferredAuthentications=publickey \
    -R0:127.0.0.1:"$PORT" "$RELAY_USER" >"$LOG" 2>&1 &
  TUNNEL_PID=$!

  URL=""
  for _ in $(seq 1 20); do
    sleep 1
    URL=$(grep -oE 'tcp://[^ ]+' "$LOG" | head -1 || true)
    [ -n "$URL" ] && break
    kill -0 "$TUNNEL_PID" 2>/dev/null || break
  done

  if [ -n "$URL" ]; then
    HOSTPORT=${URL#tcp://}
    HOST=${HOSTPORT%:*}
    publish "socks5://$USER_NAME:$PASSWORD@$HOST:${HOSTPORT##*:}"
  else
    echo "relay did not hand out a port; retrying" >&2
    sed -e 's/\x1b\[[0-9;]*m//g' "$LOG" | grep -vE 'dbind|accessibility' | tail -3 >&2
  fi

  while kill -0 "$TUNNEL_PID" 2>/dev/null; do
    sleep 5
  done
  rm -f "$LOG"
  echo "relay dropped, reconnecting" >&2
  sleep 3
done
