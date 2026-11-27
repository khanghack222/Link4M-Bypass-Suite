"""SSH keys, reachability and remote bootstrap."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

from .config import Config


class SshError(RuntimeError):
    pass


def ensure_key(cfg: Config, name: str) -> Path:
    """Create an ed25519 key once and return the private key path."""
    key = cfg.keys_dir / f"{name}.ed25519"
    if key.is_file():
        return key
    key.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", f"vpsfarm:{name}", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    key.chmod(0o600)
    return key


def public_key(key: Path) -> str:
    return Path(f"{key}.pub").read_text(encoding="utf-8").strip()


def wait_port(host: str, port: int = 22, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return
        except OSError as exc:
            last = exc
            time.sleep(3)
    raise SshError(f"{host}:{port} never opened ({last})")


def run(
    host: str,
    key: Path,
    command: str,
    user: str = "ubuntu",
    port: int = 22,
    timeout: float = 600.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    argv = [
        "ssh",
        "-i",
        str(key),
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=15",
        f"{user}@{host}",
        command,
    ]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise SshError(
            f"ssh {user}@{host} failed ({result.returncode}): {result.stderr.strip()[:400]}"
        )
    return result


def install_engine(
    host: str,
    key: Path,
    repo_url: str,
    api_key: str,
    user: str = "ubuntu",
    port: int = 22,
) -> str:
    """Run the remote bootstrap and return the service status line."""
    script = (
        "set -e; "
        f"export API_KEY={api_key}; "
        f"export REPO_URL={repo_url}; "
        "sudo -E bash -c '"
        "if [ -d /opt/l4m-engine/.git ]; then "
        "cd /opt/l4m-engine && git pull --ff-only; "
        "else git clone --depth 1 \"$REPO_URL\" /opt/l4m-engine; fi; "
        "REPO_URL=\"$REPO_URL\" API_KEY=\"$API_KEY\" "
        "bash /opt/l4m-engine/deploy/remote/bootstrap.sh' >/tmp/l4m-bootstrap.log 2>&1; "
        "systemctl is-active l4m-engine || tail -n 30 /tmp/l4m-bootstrap.log"
    )
    result = run(host, key, script, user=user, port=port, timeout=1800)
    return result.stdout.strip()


def engine_health(host: str, key: Path, user: str = "ubuntu", port: int = 22) -> bool:
    try:
        result = run(
            host,
            key,
            "curl -fsS --max-time 5 http://127.0.0.1:8080/health",
            user=user,
            port=port,
            timeout=30,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0 and "ok" in result.stdout.lower()
