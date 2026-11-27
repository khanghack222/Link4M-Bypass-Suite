"""Inventory: identities, accounts and VMs on disk with atomic writes.

Layout::

    {
      "identities": {"<id>": {...}},
      "accounts":   {"<id>": {...}},
      "vms":        {"<id>": {...}},
      "events":     [{"at": ..., "kind": ..., "detail": ...}]
    }
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Config
from .providers.base import Account, Identity, VM


class PoolError(RuntimeError):
    pass


def _blank() -> dict:
    return {"identities": {}, "accounts": {}, "vms": {}, "events": []}


class Pool:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.path = cfg.inventory_path
        if not self.path.exists():
            self._write(_blank())

    @contextmanager
    def _locked(self) -> Iterator[dict]:
        lock_path = self.path.with_suffix(".lock")
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            if not data:
                data = _blank()
            yield data
            self._write(data)
            fcntl.flock(lock, fcntl.LOCK_UN)

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        dir_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def _event(self, data: dict, kind: str, detail: str) -> None:
        data["events"].append({"at": time.time(), "kind": kind, "detail": detail})
        del data["events"][:-500]

    # --- identities ---------------------------------------------------------

    def save_identity(self, identity: Identity) -> None:
        with self._locked() as data:
            data["identities"][identity.id] = {
                "id": identity.id,
                "email": identity.email,
                "password": identity.password,
                "first_name": identity.first_name,
                "last_name": identity.last_name,
                "phone": identity.phone,
                "country": identity.country,
                "proxy": identity.proxy,
                "created_at": time.time(),
            }
            self._event(data, "identity", identity.email)
        # The plain-text copy is what `keys` and manual inspection read; the
        # inventory row above is the fast index.
        identity.dump(self.cfg.data_dir / "identities" / f"{identity.id}.json")

    def identities(self) -> list[dict]:
        return list(json.loads(self.path.read_text(encoding="utf-8"))["identities"].values())

    def identity(self, identity_id: str) -> Identity:
        path = self.cfg.data_dir / "identities" / f"{identity_id}.json"
        if path.is_file():
            return Identity.from_json(path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        row = data["identities"].get(identity_id)
        if not row:
            raise PoolError(f"no such identity: {identity_id}")
        row = dict(row)
        row.pop("created_at", None)
        return Identity(**row)

    # --- accounts -----------------------------------------------------------

    def add_account(self, account: Account) -> None:
        with self._locked() as data:
            data["accounts"][account.id] = {
                **account.__dict__,
                "created_at": account.created_at,
            }
            self._event(data, "account", f"{account.provider}:{account.email}")

    def update_account(self, account: Account) -> None:
        with self._locked() as data:
            data["accounts"][account.id] = {**account.__dict__}

    def account(self, account_id: str) -> Account:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        row = data["accounts"].get(account_id)
        if not row:
            raise PoolError(f"no such account: {account_id}")
        return Account(**row)

    def accounts(self, provider: str | None = None) -> list[Account]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = list(data["accounts"].values())
        if provider:
            rows = [row for row in rows if row.get("provider") == provider]
        return [Account(**row) for row in rows]

    # --- vms ----------------------------------------------------------------

    def add_vm(self, vm: VM) -> None:
        with self._locked() as data:
            data["vms"][vm.id] = {**vm.__dict__}
            self._event(data, "vm", f"{vm.provider}:{vm.ip}")

    def update_vm(self, vm: VM) -> None:
        with self._locked() as data:
            data["vms"][vm.id] = {**vm.__dict__}

    def vms(self, provider: str | None = None, status: str | None = None) -> list[VM]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = list(data["vms"].values())
        if provider:
            rows = [row for row in rows if row.get("provider") == provider]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [VM(**row) for row in rows]

    def vm(self, vm_id: str) -> VM:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        row = data["vms"].get(vm_id)
        if not row:
            raise PoolError(f"no such vm: {vm_id}")
        return VM(**row)

    def events(self, limit: int = 50) -> list[dict]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data["events"][-limit:]

    # --- selection ----------------------------------------------------------

    def pick_account(self, provider: str) -> Account:
        candidates = [a for a in self.accounts(provider) if a.status == "active"]
        if not candidates:
            raise PoolError(f"no active {provider} account; run `vpsfarm signup {provider}`")
        # Least recently used: `extra["last_used"]` is written by provision().
        candidates.sort(key=lambda a: float(a.extra.get("last_used", 0)))
        return candidates[0]
