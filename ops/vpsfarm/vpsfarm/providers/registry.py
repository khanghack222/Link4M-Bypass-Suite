"""Provider registry: name -> adapter."""

from __future__ import annotations

from ..config import Config
from .aws import AwsProvider
from .azure_student import AzureStudentProvider
from .base import Account, Identity, Provider, ProviderError, VM, VMSpec
from .cloudsigma import CloudSigmaProvider
from .lightning import LightningProvider
from .oracle import OracleProvider

_REGISTRY: dict[str, type[Provider]] = {
    "aws": AwsProvider,
    "oracle": OracleProvider,
    "azure-student": AzureStudentProvider,
    "azure": AzureStudentProvider,
    "cloudsigma": CloudSigmaProvider,
    "lightning": LightningProvider,
}

ALIASES = {
    "azure": "azure-student",
    "oci": "oracle",
    "oracle-cloud": "oracle",
    "lightning-ai": "lightning",
}


def names() -> list[str]:
    return sorted(_REGISTRY)


def get(cfg: Config, name: str) -> Provider:
    key = name.lower()
    key = ALIASES.get(key, key)
    try:
        factory = _REGISTRY[key]
    except KeyError:
        raise ProviderError(
            f"unknown provider: {name}; known: {', '.join(names())}"
        ) from None
    return factory(cfg)


__all__ = [
    "Account",
    "Identity",
    "Provider",
    "ProviderError",
    "VM",
    "VMSpec",
    "get",
    "names",
]
