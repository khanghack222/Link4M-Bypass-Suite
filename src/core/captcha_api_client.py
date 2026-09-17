"""
⚡ CAPTCHA SOLVER API CLIENT (v2.5.0 Omni-Precision) ⚡
Client module connecting to Local Microservice API (127.0.0.1:8000) or Cloud API on Render.
Fallback gracefully to local engines if network or server is unavailable.
"""

import os
import sys
import json
import base64
import requests
from typing import List, Dict, Any, Optional

DEFAULT_CLOUD_URL = "https://link4m-microservice-api.onrender.com"
LOCAL_URL = "http://127.0.0.1:8000"

def get_base_url() -> str:
    """Determine best available API endpoint (env var > local server > cloud fallback)."""
    if "CAPTCHA_API_URL" in os.environ:
        return os.environ["CAPTCHA_API_URL"].rstrip("/")
    # Check if local server is listening on port 8000
    try:
        r = requests.get(f"{LOCAL_URL}/health", timeout=0.4)
        if r.status_code == 200 and r.json().get("status") == "healthy":
            return LOCAL_URL
    except Exception:
        pass
    return DEFAULT_CLOUD_URL

API_KEY = os.environ.get("CAPTCHA_API_KEY", "sk_sec_fdcad6104ba10090f0b730864b123580")

def get_headers() -> dict:
    return {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

def check_health(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Check API server health status."""
    url = (base_url or get_base_url()).rstrip("/")
    try:
        r = requests.get(f"{url}/health", timeout=5)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}

def solve_qcaptcha(tile_urls: List[str], target_shape: str = "star", min_confidence: float = 0.55) -> Dict[str, Any]:
    """
    Solve QCaptcha 9-tile geometric challenge via OpenCV Omni-Precision API.
    Shapes: star, circle, triangle, hexagon, rectangle, cross.
    """
    url = get_base_url()
    payload = {
        "tile_urls": tile_urls,
        "target_shape": target_shape,
        "min_confidence": min_confidence
    }
    try:
        r = requests.post(f"{url}/api/v1/cv/analyze-tiles", json=payload, headers=get_headers(), timeout=15)
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
        r = requests.post(f"{url}/api/v1/audio/transcribe", json=payload, headers=get_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            return data.get("digit_text") or data.get("text", "")
    except Exception:
        pass
    return ""

def resolve_domain_ocr(image_url: Optional[str] = None, image_bytes: Optional[bytes] = None) -> List[str]:
    """
    Extract sponsor domain / hints from image via RapidOCR De-obfuscation API.
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
        r = requests.post(f"{url}/api/v1/ocr/resolve-domain", json=payload, headers=get_headers(), timeout=15)
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
        r = requests.post(f"{base_url}/api/v1/turnstile/solve", json=payload, headers=get_headers(), timeout=timeout_seconds + 10)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success" and data.get("token"):
                return data.get("token")
    except Exception:
        pass
    return None
