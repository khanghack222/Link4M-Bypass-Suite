"""Azure for Students: browser signup, `az` provisioning.

Signup needs a school address that passes SheerID; the adapter drives the form
and stops at the verification page. Once the subscription exists, the VM is a
plain `az vm create`, which is scriptable and idempotent.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid

from ..browser import Session, open_session
from ..config import Config
from ..mail import MailProvider
from ..ssh import ensure_key, public_key
from .base import Account, Identity, Provider, ProviderError, VM, VMSpec

SIGNUP_URL = "https://signup.azure.com/studentverification"


class AzureStudentProvider(Provider):
    name = "azure-student"
    automated_signup = False

    def signup(
        self,
        identity: Identity,
        interactive: bool = False,
        mail: MailProvider | None = None,
    ) -> Account:
        with open_session(self.cfg, identity.id) as session:
            session.goto(SIGNUP_URL, wait="networkidle", timeout=90000)
            session.fill_any(
                ['input[type="email"]', 'input[name="email"]', "#email"],
                identity.email,
            )
            session.click_any(
                ['button[type="submit"]', 'button:has-text("Next")', 'button:has-text("Continue")']
            )
            if mail is not None:
                try:
                    code = mail.wait_for_code(mail.create(local=identity.email.split("@")[0]))
                    session.fill_any(
                        ['input[autocomplete="one-time-code"]', 'input[name="code"]'], code
                    )
                    session.click_any(['button[type="submit"]', 'button:has-text("Verify")'])
                except Exception:
                    pass
            if interactive:
                print("complete SheerID verification and the subscription form, then press Enter")
                input()
            else:
                raise ProviderError(
                    "azure-student signup needs a human at the SheerID step; "
                    "re-run with --interactive"
                )

        return Account(
            id=uuid.uuid4().hex[:16],
            provider=self.name,
            email=identity.email,
            password=identity.password,
            identity_id=identity.id,
            extra={"location": self.cfg.azure_location},
        )

    def _az(self, *args: str, timeout: float = 600.0) -> dict:
        result = subprocess.run(
            ["az", *args, "--output", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise ProviderError(f"az {' '.join(args[:2])} failed: {result.stderr.strip()[:400]}")
        return json.loads(result.stdout or "{}")

    def provision(self, account: Account, spec: VMSpec) -> VM:
        location = spec.region or account.extra.get("location") or self.cfg.azure_location
        size = spec.instance_type or self.cfg.azure_vm_size
        group = spec.name or f"l4m-{uuid.uuid4().hex[:6]}"
        key_name = f"azure-{uuid.uuid4().hex[:8]}"
        key_path = ensure_key(self.cfg, key_name)

        self._az("group", "create", "--name", group, "--location", location)
        created = self._az(
            "vm",
            "create",
            "--resource-group",
            group,
            "--name",
            f"{group}-vm",
            "--image",
            "Ubuntu2404",
            "--size",
            size,
            "--location",
            location,
            "--admin-username",
            "ubuntu",
            "--ssh-key-values",
            public_key(key_path),
            "--public-ip-sku",
            "Standard",
            "--nsg-rule",
            "SSH",
        )
        ip = (
            created.get("publicIpAddress")
            or self._az(
                "vm", "list-ip-addresses", "--resource-group", group, "--name", f"{group}-vm"
            )
        )
        if isinstance(ip, dict):
            try:
                ip = ip["publicIpAddresses"][0]["ipAddress"]
            except (KeyError, IndexError):
                ip = ""
        account.extra["last_used"] = time.time()
        return VM(
            id=f"{group}/{group}-vm",
            provider=self.name,
            account_id=account.id,
            ip=str(ip or ""),
            ssh_user="ubuntu",
            ssh_port=22,
            key_name=str(key_path),
            region=location,
            specs=size,
            extra={"resource_group": group},
        )

    def destroy(self, account: Account, vm: VM) -> None:
        group = vm.extra.get("resource_group") or vm.id.split("/")[0]
        self._az("group", "delete", "--name", group, "--yes", "--no-wait")

    def list_vms(self, account: Account) -> list[VM]:
        rows = self._az("vm", "list", "--show-details")
        out: list[VM] = []
        for row in rows if isinstance(rows, list) else []:
            out.append(
                VM(
                    id=f"{row['resourceGroup']}/{row['name']}",
                    provider=self.name,
                    account_id=account.id,
                    ip=row.get("publicIps", ""),
                    ssh_user="ubuntu",
                    ssh_port=22,
                    key_name="",
                    region=row.get("location", ""),
                    specs=row.get("hardwareProfile", {}).get("vmSize", ""),
                    status=str(row.get("powerState", "")),
                    extra={"resource_group": row["resourceGroup"]},
                )
            )
        return out
