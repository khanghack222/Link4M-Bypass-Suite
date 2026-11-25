#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-import fast-path decoder.

Kept dependency-free on purpose: the CLI measures this call inside its own
``time_ms`` budget, and importing ``runner_registry`` would drag in Playwright
(~1.2s cold) before a single byte of URL is decoded.
"""

import base64
import re
import urllib.parse
from typing import Optional

_GO_FILE = re.compile(r"/go/file/([A-Za-z0-9_\-%]+)")
_SELF_REF = ("link4m", "bbmkts", "trafficvn", "yeumoney")


def _normalize(url: str) -> str:
    u = (url or "").strip()
    if u and "://" not in u:
        u = "https://" + u.lstrip("/")
    return u


def _try_b64(s: str) -> Optional[str]:
    try:
        pad = (-len(s)) % 4
        dec = base64.b64decode(s + ("=" * pad)).decode("utf-8", errors="ignore")
        return dec if dec.startswith("http") else None
    except Exception:
        return None


def fast_decode(url: str) -> Optional[str]:
    """Resolve zero-browser shapes: /go/file/<b64|pct>, query/hash base64."""
    u = _normalize(url)
    m = _GO_FILE.search(u)
    if m:
        part = urllib.parse.unquote(m.group(1))
        for candidate in (part, urllib.parse.unquote(part)):
            got = _try_b64(candidate)
            if got and not any(k in got.lower() for k in _SELF_REF):
                return got
            if candidate.startswith("http") and not any(k in candidate.lower() for k in _SELF_REF):
                return candidate
    try:
        parsed = urllib.parse.urlparse(u)
        values = [v for vals in urllib.parse.parse_qs(parsed.query).values() for v in vals]
        if parsed.fragment:
            values.append(parsed.fragment)
    except Exception:
        return None
    for v in values:
        if len(v) <= 16:
            continue
        got = _try_b64(v)
        if got and not any(k in got.lower() for k in _SELF_REF):
            return got
    return None
