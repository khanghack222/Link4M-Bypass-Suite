"""Provider contracts shared by every adapter."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..browser import Session
from ..config import Config


class ProviderError(RuntimeError):
    pass


@dataclass
class Identity:
    id: str
    email: str
    password: str
    first_name: str = "Alex"
    last_name: str = "Tran"
    phone: str = ""
    country: str = "VN"
    proxy: str = ""

    @classmethod
    def from_json(cls, path: Path) -> "Identity":
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        path.chmod(0o600)


@dataclass
class Account:
    id: str
    provider: str
    email: str
    password: str
    identity_id: str
    created_at: float = field(default_factory=time.time)
    status: str = "active"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400


@dataclass
class VM:
    id: str
    provider: str
    account_id: str
    ip: str
    ssh_user: str
    ssh_port: int
    key_name: str
    region: str
    specs: str
    created_at: float = field(default_factory=time.time)
    status: str = "running"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VMSpec:
    region: str = ""
    instance_type: str = ""
    image: str = ""
    name: str = ""
    user_data: str = ""


class Provider:
    name = "base"
    #: Whether the signup step is expected to run without a human click.
    automated_signup = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # --- signup -------------------------------------------------------------

    def signup(self, identity: Identity, interactive: bool = False) -> Account:
        """Drive the provider's signup form with a fresh browser profile."""
        raise NotImplementedError(f"{self.name} has no signup adapter")

    # --- compute ------------------------------------------------------------

    def provision(self, account: Account, spec: VMSpec) -> VM:
        raise NotImplementedError(f"{self.name} has no provision adapter")

    def destroy(self, account: Account, vm: VM) -> None:
        raise NotImplementedError(f"{self.name} cannot destroy {vm.id}")

    def list_vms(self, account: Account) -> list[VM]:
        return []
