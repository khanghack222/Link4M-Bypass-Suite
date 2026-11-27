"""Configuration: TOML file plus VPSFARM_* environment overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get("VPSFARM_CONFIG", "~/.config/vpsfarm/config.toml")
).expanduser()


def _expand(value: str) -> str:
    return str(Path(value).expanduser()) if value.startswith("~") else value


@dataclass
class Config:
    data_dir: Path = field(
        default_factory=lambda: Path("~/.local/share/vpsfarm").expanduser()
    )

    mail_provider: str = "cloudflare"
    mail_domain: str = ""
    mail_worker_url: str = ""
    mail_secret: str = ""

    sms_provider: str = "5sim"
    sms_key: str = ""
    sms_country: str = "vietnam"
    sms_product: str = "other"

    captcha_provider: str = "capsolver"
    captcha_key: str = ""

    proxy: str = ""
    headless: bool = False
    browser_engine: str = "patchright"

    aws_region: str = "ap-southeast-1"
    aws_instance_type: str = "t3.small"

    oci_config: str = "~/.oci/config"
    oci_profile: str = "DEFAULT"
    oci_compartment: str = ""
    oci_shape: str = "VM.Standard.A1.Flex"
    oci_ocpus: int = 4
    oci_memory_gb: int = 24

    azure_location: str = "southeastasia"
    azure_vm_size: str = "Standard_B2ats_v2"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def inventory_path(self) -> Path:
        return self.data_dir / "inventory.json"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.profiles_dir, self.keys_dir):
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(0o700)


# Every key in Config is also an override point: VPSFARM_MAIL_DOMAIN etc.
_ENV_MAP = {
    "DATA_DIR": "data_dir",
    "MAIL_PROVIDER": "mail_provider",
    "MAIL_DOMAIN": "mail_domain",
    "MAIL_WORKER_URL": "mail_worker_url",
    "MAIL_SECRET": "mail_secret",
    "SMS_PROVIDER": "sms_provider",
    "SMS_KEY": "sms_key",
    "SMS_COUNTRY": "sms_country",
    "SMS_PRODUCT": "sms_product",
    "CAPTCHA_PROVIDER": "captcha_provider",
    "CAPTCHA_KEY": "captcha_key",
    "PROXY": "proxy",
    "HEADLESS": "headless",
    "BROWSER_ENGINE": "browser_engine",
    "AWS_REGION": "aws_region",
    "AWS_INSTANCE_TYPE": "aws_instance_type",
    "OCI_CONFIG": "oci_config",
    "OCI_PROFILE": "oci_profile",
    "OCI_COMPARTMENT": "oci_compartment",
    "OCI_SHAPE": "oci_shape",
    "OCI_OCPUS": "oci_ocpus",
    "OCI_MEMORY_GB": "oci_memory_gb",
    "AZURE_LOCATION": "azure_location",
    "AZURE_VM_SIZE": "azure_vm_size",
}

_BOOL_KEYS = {"headless"}
_INT_KEYS = {"oci_ocpus", "oci_memory_gb"}


def load(path: Path | None = None) -> Config:
    cfg = Config()
    target = path or CONFIG_PATH
    if target.is_file():
        with target.open("rb") as handle:
            raw = tomllib.load(handle)
        for key, value in raw.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    for env_name, attr in _ENV_MAP.items():
        value = os.environ.get(f"VPSFARM_{env_name}")
        if value is None:
            continue
        if attr in _BOOL_KEYS:
            value = value not in {"0", "false", "False", ""}
        elif attr in _INT_KEYS:
            value = int(value)
        setattr(cfg, attr, value)
    if isinstance(cfg.data_dir, str):
        cfg.data_dir = Path(_expand(cfg.data_dir))
    cfg.ensure_dirs()
    return cfg
