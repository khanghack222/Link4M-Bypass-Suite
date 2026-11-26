"""
⚡ OCILAR CAPTCHA SOLVER API CLIENT ⚡
Official Ocilar API Integration for Cloudflare Turnstile & SAT Captcha.
Endpoint: https://api.ocilar.com/api/v1
Sub-200ms OCR execution and instant remote Turnstile token generation.
"""

import os
import json
import base64
import time
import requests
from typing import Optional, Dict, Any

OCILAR_BASE_URL = "https://api.ocilar.com/api/v1"
OCILAR_API_KEY = os.environ.get("OCILAR_API_KEY", "").strip()

_SESSION = requests.Session()
_HEADERS = {
    "X-API-Key": OCILAR_API_KEY,
    "Content-Type": "application/json"
}


def is_ocilar_configured() -> bool:
    return bool(OCILAR_API_KEY and OCILAR_API_KEY.startswith("sk-"))


def check_ocilar_quota() -> Dict[str, Any]:
    """Check remaining balance and quota on Ocilar API."""
    if not is_ocilar_configured():
        return {}
    try:
        r = _SESSION.get(f"{OCILAR_BASE_URL}/user", headers=_HEADERS, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def solve_turnstile_ocilar(page_url: str, sitekey: str, timeout: float = 20.0) -> Optional[str]:
    """
    Solve Cloudflare Turnstile challenge remotely via Ocilar API.
    Returns the solved cf-turnstile-response token string or None.
    """
    if not is_ocilar_configured() or not sitekey:
        return None

    payload = {
        "sitekey": sitekey,
        "url": page_url
    }
    try:
        t0 = time.time()
        r = _SESSION.post(
            f"{OCILAR_BASE_URL}/solve/cloudflare",
            json=payload,
            headers=_HEADERS,
            timeout=timeout
        )
        if r.status_code == 200:
            data = r.json()
            token = data.get("token") or data.get("solution") or data.get("response")
            if token:
                elapsed = round(time.time() - t0, 2)
                try:
                    print(f"[+] [Ocilar Cloud] Turnstile solved in {elapsed}s: {token[:35]}...", flush=True)
                except Exception:
                    pass
                return token
    except Exception as e:
        try:
            print(f"[!] Ocilar Turnstile note: {e}", flush=True)
        except Exception:
            pass
    return None


def solve_image_sat_ocilar(img_bytes: bytes, timeout: float = 5.0) -> Optional[str]:
    """
    Solve SAT / Distorted alphanumeric image captcha in ~180ms via Ocilar API.
    """
    if not is_ocilar_configured() or not img_bytes:
        return None

    try:
        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        payload = {"image": b64_str}
        t0 = time.time()
        r = _SESSION.post(
            f"{OCILAR_BASE_URL}/solve/sat",
            json=payload,
            headers=_HEADERS,
            timeout=timeout
        )
        if r.status_code == 200:
            data = r.json()
            txt = data.get("text", "").strip()
            latency = data.get("latency_ms", round((time.time() - t0) * 1000, 1))
            if txt:
                try:
                    print(f"[+] [Ocilar SAT] Image captcha solved in {latency}ms: '{txt}'", flush=True)
                except Exception:
                    pass
                return txt
    except Exception as e:
        try:
            print(f"[!] Ocilar SAT note: {e}", flush=True)
        except Exception:
            pass
    return None
