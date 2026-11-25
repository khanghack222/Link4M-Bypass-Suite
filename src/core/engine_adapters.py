#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ENGINE ADAPTERS — THE ONLY PLACE THAT KNOWS ENGINE CALL SIGNATURES ⚡

Every engine in the suite returns a different shape (str, dict, Node promise
JSON) and has import-time side effects. These shims isolate that knowledge:
imports are lazy, results are normalised to ``str | None`` via ``dest_from``.
"""

import json
import os
import shutil
import subprocess
from typing import Any, Optional


def dest_from(value: Any) -> Optional[str]:
    """Normalise every engine return shape to a destination string or None."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v or None
    if not isinstance(value, dict):
        return None
    if value.get("ok") is False or value.get("success") is False:
        return None
    for key in ("finalUrl", "final_url", "destination", "destination_url",
                "url", "link", "href"):
        got = value.get(key)
        if isinstance(got, str) and got.strip():
            return got.strip()
    dl = value.get("data_link")
    if isinstance(dl, dict):
        got = dl.get("url")
        if isinstance(got, str) and got.strip():
            return got.strip()
    elif isinstance(dl, str) and dl.strip():
        return dl.strip()
    return None


def run_bbmkts(url: str, headless: bool = True) -> Optional[str]:
    import bbmkts_runner  # noqa: WPS433 - engine import must stay lazy
    return dest_from(bbmkts_runner.run(url, headless=headless))


def run_gtraffic(url: str, headless: bool = True) -> Optional[str]:
    import gtraffic_runner  # noqa: WPS433
    return dest_from(gtraffic_runner.run(url, headless=headless))


def run_layma(url: str, headless: bool = True) -> Optional[str]:
    import layma_runner  # noqa: WPS433
    return dest_from(layma_runner.run(url, headless=headless))


def run_trafficvn(url: str, headless: bool = True) -> Optional[str]:
    import trafficvn_runner  # noqa: WPS433
    return dest_from(trafficvn_runner.run(url, headless=headless))


def run_link4m_legacy(url: str, headless: bool = True,
                      proxy: Optional[str] = None) -> Optional[str]:
    import bypass  # noqa: WPS433 - bypass re-execs at import, never module scope
    return dest_from(bypass.run(url, headless=headless, proxy=proxy))


def run_link4m_cdp(alias: str, keep_open: bool = False) -> Optional[str]:
    import link4m_engine  # noqa: WPS433
    return dest_from(link4m_engine.bypass_alias(alias, keep_open=keep_open))


def _node_bin() -> str:
    return shutil.which("node") or "node"


def run_octolink(url: str, headless: bool = True, timeout: int = 480) -> Optional[str]:
    """Run octolink_runner.js and read its trailing JSON line from stdout.

    The JS runner prints human log lines and, since the registry change, one
    JSON object at the end. Scanning backwards keeps the parser immune to
    engine log noise.
    """
    js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "octolink_runner.js")
    cmd = [_node_bin(), js, url]
    if headless:
        cmd.append("--headless")
    cmd.append("--json")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            got = dest_from(payload)
            if got:
                return got
    return None
