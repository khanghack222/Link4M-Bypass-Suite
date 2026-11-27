"""Provider adapters and the name -> adapter registry."""

from __future__ import annotations

from .base import Account, Identity, Provider, ProviderError, VM, VMSpec
from .registry import ALIASES, get, names

__all__ = [
    "ALIASES",
    "Account",
    "Identity",
    "Provider",
    "ProviderError",
    "VM",
    "VMSpec",
    "get",
    "names",
]
