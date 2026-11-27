"""Lightning AI Studios: 4 vCPU / 16 GB, no card, restarts every 4 h.

Not a VPS: the studio is a container that Lightning recycles on a timer. The
adapter creates a studio through the CLI and returns a VM-shaped record whose
``extra["cli"]`` is the command that opens a shell. Use it for Chrome work that
can survive a restart (the engine resumes from data/queue.json), not for a
long-lived public service.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid

from ..config import Config
from .base import Account, Identity, Provider, ProviderError, VM, VMSpec


class LightningProvider(Provider):
    name = "lightning"
    automated_signup = False

    def _cli(self, *args: str, timeout: float = 600.0) -> str:
        binary = shutil.which("lightning")
        if not binary:
            raise ProviderError(
                "lightning CLI missing: pip install lightning-sdk && lightning login"
            )
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            raise ProviderError(f"lightning {' '.join(args[:2])}: {result.stderr.strip()[:400]}")
        return result.stdout.strip()

    def signup(self, identity: Identity, interactive: bool = False) -> Account:
        raise ProviderError("lightning signup is a web login; run `lightning login` once")

    def provision(self, account: Account, spec: VMSpec) -> VM:
        name = spec.name or f"l4m-{uuid.uuid4().hex[:6]}"
        raw = self._cli("studio", "create", "--name", name, "--no-open")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"name": name, "raw": raw}
        studio = payload.get("name") or name
        return VM(
            id=studio,
            provider=self.name,
            account_id=account.id,
            ip="",
            ssh_user="",
            ssh_port=0,
            key_name="",
            region=payload.get("region", ""),
            specs="4 vCPU / 16 GB (restart every 4 h)",
            extra={
                "cli": f"lightning studio ssh {studio}",
                "install": (
                    "sudo apt-get update && sudo apt-get install -y xvfb "
                    "&& git clone $REPO_URL /opt/l4m-engine "
                    "&& cd /opt/l4m-engine && bash deploy/remote/bootstrap.sh"
                ),
            },
        )

    def destroy(self, account: Account, vm: VM) -> None:
        self._cli("studio", "delete", "--name", vm.id, "--yes")

    def list_vms(self, account: Account) -> list[VM]:
        raw = self._cli("studio", "list", "--json")
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            return []
        out: list[VM] = []
        for row in rows if isinstance(rows, list) else []:
            out.append(
                VM(
                    id=row.get("name", ""),
                    provider=self.name,
                    account_id=account.id,
                    ip="",
                    ssh_user="",
                    ssh_port=0,
                    key_name="",
                    region=row.get("region", ""),
                    specs="4 vCPU / 16 GB",
                    status=row.get("status", "running"),
                    extra={"cli": f"lightning studio ssh {row.get('name', '')}"},
                )
            )
        return out
