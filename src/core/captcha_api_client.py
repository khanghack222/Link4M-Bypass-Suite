"""
⚡ CAPTCHA SOLVER API CLIENT (v3.1.0 Turbo Sub-0.1s) ⚡
Client module connecting to Local Microservice API (127.0.0.1:8000) or Cloud API on Render.
Optimized with connection pooling, cached endpoint resolution, and sub-100ms execution.
"""

import os
import sys
import time
import json
import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from typing import List, Dict, Any, Optional

DEFAULT_CLOUD_URL = "https://link4m-microservice-api.onrender.com"
LOCAL_URL = "http://127.0.0.1:8000"

_RESOLVED_BASE_URL: Optional[str] = None
_LAST_HEALTH_CHECK_TIME = 0.0
_HEALTH_CHECK_TTL = 30.0 # Re-check endpoint every 30s instead of on every request

# Persistent Pooled HTTP Session
_SESSION = requests.Session()
_retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=_retries, pool_connections=20, pool_maxsize=20)
_SESSION.mount("https://", _adapter)
_SESSION.mount("http://", _adapter)

API_KEY = os.environ.get("CAPTCHA_API_KEY", "sk_sec_fdcad6104ba10090f0b730864b123580")
_HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def get_base_url(force_refresh: bool = False) -> str:
    """Determine best available API endpoint (cached for 30s to avoid redundant pings)."""
    global _RESOLVED_BASE_URL, _LAST_HEALTH_CHECK_TIME

    if "CAPTCHA_API_URL" in os.environ:
        return os.environ["CAPTCHA_API_URL"].rstrip("/")

    now = time.time()
    if not force_refresh and _RESOLVED_BASE_URL and (now - _LAST_HEALTH_CHECK_TIME < _HEALTH_CHECK_TTL):
        return _RESOLVED_BASE_URL

    # Test local fast loopback
    try:
        r = _SESSION.get(f"{LOCAL_URL}/health", timeout=0.2)
        if r.status_code == 200 and r.json().get("status") == "healthy":
            _RESOLVED_BASE_URL = LOCAL_URL
            _LAST_HEALTH_CHECK_TIME = now
            return LOCAL_URL
    except Exception:
        pass

    _RESOLVED_BASE_URL = DEFAULT_CLOUD_URL
    _LAST_HEALTH_CHECK_TIME = now
    return DEFAULT_CLOUD_URL

def check_health(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Check API server health status."""
    url = (base_url or get_base_url()).rstrip("/")
    try:
        r = _SESSION.get(f"{url}/health", timeout=5)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}

def solve_qcaptcha(tile_urls: List[str], target_shape: str = "star", min_confidence: float = 0.55) -> Dict[str, Any]:
    """
    Solve QCaptcha 9-tile geometric challenge via OpenCV Omni-Precision API (<50ms).
    Shapes: star, circle, triangle, hexagon, rectangle, cross.
    """
    # Priority 0: Fast Local OpenCV Engine (Sub-15ms, Zero Network Lag)
    try:
        from src.core.qcaptcha_engine import extract_tile_features, solve_qcaptcha_tiles
        import requests, io
        from concurrent.futures import ThreadPoolExecutor

        def fetch_tile(url):
            try:
                r = _SESSION.get(url, timeout=3)
                return r.content
            except Exception:
                return b""

        with ThreadPoolExecutor(max_workers=len(tile_urls)) as pool:
            raw_images = list(pool.map(fetch_tile, tile_urls))

        features = [extract_tile_features(b) for b in raw_images]
        target_indices = solve_qcaptcha_tiles(features, question_text=target_shape, challenge_type="grid3x3", spec={})
        if target_indices:
            return {
                "correct_indices": target_indices,
                "tiles": [{"idx": i, "shape": f.get("shape")} for i, f in enumerate(features)],
                "status": "success",
                "engine": "local_qcaptcha_v4"
            }
    except Exception:
        pass

    # Priority 1: Cloud Microservice (Timeout 2.0s)
    url = get_base_url()
    payload = {
        "tile_urls": tile_urls,
        "target_shape": target_shape,
        "min_confidence": min_confidence
    }
    try:
        r = _SESSION.post(f"{url}/api/v1/cv/analyze-tiles", json=payload, headers=_HEADERS, timeout=2.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"correct_indices": [], "status": "error"}

def solve_audio_recaptcha(audio_url: Optional[str] = None, audio_bytes: Optional[bytes] = None) -> str:
    """
    Solve reCAPTCHA Audio challenge via DSP Filter + Whisper / Google Speech API.
    Returns digit string (e.g. '72841').
    """
    url = get_base_url()
    payload = {
        "language": "en-US",
        "apply_dsp_filter": True
    }
    if audio_url:
        payload["audio_url"] = audio_url
    elif audio_bytes:
        payload["audio_base64"] = base64.b64encode(audio_bytes).decode('utf-8')
    else:
        return ""

    try:
        r = _SESSION.post(f"{url}/api/v1/audio/transcribe", json=payload, headers=_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("digit_text") or data.get("text", "")
    except Exception:
        pass
    return ""

def resolve_domain_ocr(image_url: Optional[str] = None, image_bytes: Optional[bytes] = None) -> List[str]:
    """
    Extract sponsor domain / hints from image via RapidOCR De-obfuscation API (<50ms).
    """
    url = get_base_url()
    payload = {}
    if image_url:
        payload["image_url"] = image_url
    elif image_bytes:
        payload["image_base64"] = base64.b64encode(image_bytes).decode('utf-8')
    else:
        return []

    try:
        r = _SESSION.post(f"{url}/api/v1/ocr/resolve-domain", json=payload, headers=_HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("domains", [])
    except Exception:
        pass
    return []

def solve_turnstile_cloud(url: str, sitekey: str, timeout_seconds: int = 30) -> Optional[str]:
    """
    Solve Cloudflare Turnstile token via Microservice API.
    """
    base_url = get_base_url()
    payload = {
        "url": url,
        "sitekey": sitekey,
        "headless": True,
        "timeout_seconds": timeout_seconds
    }
    try:
        r = _SESSION.post(f"{base_url}/api/v1/turnstile/solve", json=payload, headers=_HEADERS, timeout=timeout_seconds + 5)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success" and data.get("token"):
                return data.get("token")
    except Exception:
        pass
    return None
