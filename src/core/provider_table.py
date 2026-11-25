#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ SINGLE SOURCE OF TRUTH FOR SHORTLINK PROVIDERS ⚡
Declares every supported provider once: canonical key, alias spellings, hosts,
URL pattern and engine kind. Deliberately data-only — it must never import
``runners.py`` (the registry imports both and resolves runner classes lazily),
so this module stays import-safe from every face, including ``--list``.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class EngineKind(str, Enum):
    BROWSER = "browser"            # in-process Playwright/patchright engine module
    EXTERNAL_NODE = "external_node"  # Node subprocess (octolink_runner.js)
    DECODE = "decode"              # pure string/base64 resolution, no browser, no network


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    aliases: Tuple[str, ...]
    hosts: Tuple[str, ...]
    url_pattern: Optional[re.Pattern]
    kind: EngineKind
    module: str
    note: str = ""
    ready: bool = True

    @property
    def runner(self):
        """Resolve the runner class lazily through the registry.

        Keeping this a property avoids the provider_table -> runners -> registry
        import cycle: the table stores no class object, the registry owns that
        mapping.
        """
        return _resolve_runner(self.key)


def _resolve_runner(key: str):
    import sys

    registry = sys.modules.get("runner_registry") or sys.modules.get("src.core.runner_registry")
    if registry is None:
        try:
            import runner_registry as registry  # noqa: WPS433
        except ImportError:  # pragma: no cover - package import path
            from src.core import runner_registry as registry  # noqa: WPS433
    return registry.get_runner(key)


# Canonical key -> every historical / face-local spelling that must resolve to it.
PROVIDER_ALIASES = {
    "LINK4M":    ("LINK4M", "LINK4", "L4M"),
    "BBMKTS":    ("BBMKTS", "BBMKT", "YOUMONEY", "YEUMONEY"),
    "GTRAFFIC":  ("GTRAFFIC", "G-TRAFFIC", "DIRECT_GTRAFFIC"),
    "LAYMA":     ("LAYMA", "LAYMA.NET"),
    "TRAFFICVN": ("TRAFFICVN", "TRAFFIC_VN", "IATUM"),
    "OCTOLINK":  ("OCTOLINK", "OCTO", "LINK999", "UPTOLINK",
                  "LINKHUONGDAN", "SHORTEARN"),
    "DECODE":    ("DECODE", "BASE64", "FASTPATH"),
}

GENERIC_KEY = "GENERIC"

LINK4M_HOSTS = (
    "link4m.net", "link4m.com", "link4m.co", "link4m.org",
    "link4m.vip", "link4m.pro", "link4m.me", "link4m.app",
)

PROVIDER_TABLE: Tuple[ProviderSpec, ...] = (
    ProviderSpec(
        key="LINK4M",
        aliases=PROVIDER_ALIASES["LINK4M"],
        hosts=LINK4M_HOSTS,
        url_pattern=re.compile(r"/go/([A-Za-z0-9_-]+)"),
        kind=EngineKind.BROWSER,
        module="bypass / link4m_engine",
        note="sponsor OCR + reCAPTCHA audio",
    ),
    ProviderSpec(
        key="BBMKTS",
        aliases=PROVIDER_ALIASES["BBMKTS"],
        hosts=("bbmkts.com", "yeumoney.com"),
        url_pattern=re.compile(r"/go/([A-Za-z0-9_-]+)"),
        kind=EngineKind.BROWSER,
        module="bbmkts_runner",
        note="dual-tab countdown + route patch",
    ),
    ProviderSpec(
        key="GTRAFFIC",
        aliases=PROVIDER_ALIASES["GTRAFFIC"],
        hosts=("gtraffic.io", "direct.gtraffic.io", "dr-client.gtraffic.io",
               "client.gtraffic.io"),
        url_pattern=re.compile(r"/([A-Za-z0-9_-]+)$"),
        kind=EngineKind.BROWSER,
        module="gtraffic_runner",
        note="mobile viewport + API leak",
    ),
    ProviderSpec(
        key="LAYMA",
        aliases=PROVIDER_ALIASES["LAYMA"],
        hosts=("layma.net",),
        url_pattern=re.compile(r"/([A-Za-z0-9_-]+)$"),
        kind=EngineKind.BROWSER,
        module="layma_runner",
        note="qcaptcha stealth + HSV vision",
    ),
    ProviderSpec(
        key="TRAFFICVN",
        aliases=PROVIDER_ALIASES["TRAFFICVN"],
        hosts=("trafficvn.com", "trafficvn.net"),
        url_pattern=re.compile(r"/(?:get/)?([A-Za-z0-9_-]+)"),
        kind=EngineKind.BROWSER,
        module="trafficvn_runner",
        note="countdown + activation code",
    ),
    ProviderSpec(
        key="OCTOLINK",
        aliases=PROVIDER_ALIASES["OCTOLINK"],
        # Prefix entries (trailing dot) cover the rotating brand subdomains
        # uptolink.* / linkhuongdan.* without listing every TLD.
        hosts=("octolink.vip", "link999.app", "link999.com", "uptolink.",
               "linkhuongdan.", "shortearn.net"),
        url_pattern=None,  # slug form varies per brand
        kind=EngineKind.EXTERNAL_NODE,
        module="octolink_runner.js",
        note="canvas physics + hold captcha",
    ),
    ProviderSpec(
        key="DECODE",
        aliases=PROVIDER_ALIASES["DECODE"],
        hosts=(),
        url_pattern=None,
        kind=EngineKind.DECODE,
        module="runner_registry.fast_decode",
        note="base64/pct fast path, no browser",
    ),
)


def spec_for(key: str) -> Optional[ProviderSpec]:
    """Alias-aware, case-insensitive lookup: ``"link999"`` -> OCTOLINK spec."""
    if not key or not isinstance(key, str):
        return None
    needle = key.strip().upper()
    if not needle:
        return None
    for spec in PROVIDER_TABLE:
        if needle == spec.key or needle in spec.aliases:
            return spec
    return None


def canonical_key(raw: str) -> Optional[str]:
    """Alias -> canonical key, ``None`` when unknown."""
    spec = spec_for(raw)
    return spec.key if spec else None


def table_by_key() -> dict:
    return {spec.key: spec for spec in PROVIDER_TABLE}
