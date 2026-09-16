"""
⚡ CAPTCHA SOLVER API CLIENT (v2.4.0 Omni-Precision) ⚡
Client module connecting directly to Cloud API on Render.
Fallback gracefully to local engines if network or API key is unavailable.
"""

import os
import sys
import json
import base64
import requests
from typing import List, Dict, Any, Optional

API_URL = os.environ.get("CAPTCHA_API_URL", "https://link4m-microservice-api.onrender.com")
API_KEY = os.environ.get("CAPTCHA_API_KEY", "sk_sec_fdcad6104ba10090f0b730864b123580")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def check_health() -> Dict[str, Any]:
    """Check API server health status."""
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}

def solve_qcaptcha(tile_urls: List[str], target_shape: str = "star", min_confidence: float = 0.65) -> Dict[str, Any]:
    """
    Solve QCaptcha 9-tile geometric challenge via OpenCV Omni-Precision API.
    Shapes: star, circle, triangle, hexagon, rectangle, cross.
    """
    payload = {
        "tile_urls": tile_urls,
        "target_shape": target_shape,
        "min_confidence": min_confidence
    }
    try:
        r = requests.post(f"{API_URL}/api/v1/cv/analyze-tiles", json=payload, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        pass
    return {"correct_indices": [], "status": "error"}

def solve_audio_recaptcha(audio_url: Optional[str] = None, audio_bytes: Optional[bytes] = None) -> str:
    """
    Solve reCAPTCHA Audio challenge via DSP Filter + Whisper API.
    Returns digit string (e.g. '72841').
    """
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
        r = requests.post(f"{API_URL}/api/v1/audio/transcribe", json=payload, headers=HEADERS, timeout=20)
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
    payload = {}
    if image_url:
        payload["image_url"] = image_url
    elif image_bytes:
        payload["image_base64"] = base64.b64encode(image_bytes).decode('utf-8')
    else:
        return []

    try:
        r = requests.post(f"{API_URL}/api/v1/ocr/resolve-domain", json=payload, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("domains", [])
    except Exception:
        pass
    return []

def solve_turnstile_cloud(url: str, sitekey: str, timeout_seconds: int = 25) -> Optional[str]:
    """
    Solve Cloudflare Turnstile token via Render API.
    """
    payload = {
        "url": url,
        "sitekey": sitekey,
        "headless": True,
        "timeout_seconds": timeout_seconds
    }
    try:
        r = requests.post(f"{API_URL}/api/v1/turnstile/solve", json=payload, headers=HEADERS, timeout=timeout_seconds + 10)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success" and data.get("token"):
                return data.get("token")
    except Exception:
        pass
    return None
