"""
⚡ WEBAI-TO-API INTEGRATION FOR OCR & VISION SOLVER ⚡
Connects Link4M Bypass Suite to WebAI-to-API server (http://127.0.0.1:6969)
Provides zero-cost, high-precision Gemini Vision OCR, mission screenshot analysis,
domain de-obfuscation, and captcha solving.
"""

import os
import re
import json
import time
import base64
import requests
from typing import List, Dict, Any, Optional

WEBAI_DEFAULT_URL = os.environ.get("WEBAI_API_URL", "http://127.0.0.1:6969").rstrip("/")
WEBAI_MODEL = os.environ.get("WEBAI_MODEL", "gemini-3-flash")

_SESSION = requests.Session()
_SESSION.trust_env = False  # Avoid proxy interception on localhost

_IS_AVAILABLE: Optional[bool] = None
_LAST_CHECK_TIME = 0.0
_HEALTH_TTL = 20.0  # Cache health check for 20s


def is_webai_available(force_check: bool = False) -> bool:
    """Check if local WebAI-to-API server is online with fast cached response."""
    global _IS_AVAILABLE, _LAST_CHECK_TIME
    now = time.time()
    if not force_check and _IS_AVAILABLE is not None and (now - _LAST_CHECK_TIME < _HEALTH_TTL):
        return _IS_AVAILABLE

    try:
        r = _SESSION.get(f"{WEBAI_DEFAULT_URL}/health", timeout=0.5)
        if r.status_code == 200:
            _IS_AVAILABLE = True
            _LAST_CHECK_TIME = now
            return True
    except Exception:
        pass

    # Alternative check: /v1/models
    try:
        r = _SESSION.get(f"{WEBAI_DEFAULT_URL}/v1/models", timeout=0.5)
        if r.status_code == 200:
            _IS_AVAILABLE = True
            _LAST_CHECK_TIME = now
            return True
    except Exception:
        pass

    _IS_AVAILABLE = False
    _LAST_CHECK_TIME = now
    return False


def _call_webai_chat(messages: List[Dict[str, Any]], model: Optional[str] = None, timeout: float = 35.0) -> str:
    """Send chat completions request to WebAI-to-API server."""
    if not is_webai_available():
        return ""

    target_model = model or WEBAI_MODEL
    payload = {
        "model": target_model,
        "messages": messages
    }

    # Primary endpoint: /v1/chat/completions; Fallback: /v1/stateless/chat/completions
    for ep in ("/v1/chat/completions", "/v1/stateless/chat/completions"):
        try:
            r = _SESSION.post(f"{WEBAI_DEFAULT_URL}{ep}", json=payload, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
        except Exception:
            continue
    return ""


def _extract_json_from_text(text: str) -> Optional[dict]:
    """Extract and parse JSON object from markdown or conversational LLM text."""
    if not text:
        return None
    # 1. Match ```json { ... } ``` or ``` { ... } ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 2. Match outermost { ... }
    m2 = re.search(r"\{[\s\S]*\}", text)
    if m2:
        try:
            return json.loads(m2.group(0))
        except Exception:
            pass
    # 3. Direct loads
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    return None


def ocr_image_webai(img_bytes: bytes, prompt: Optional[str] = None) -> str:
    """
    Perform high-accuracy OCR on image bytes using WebAI-to-API (Gemini Vision).
    Extracts Vietnamese and English text with zero character loss.
    """
    if not img_bytes or len(img_bytes) < 50:
        return ""

    if not is_webai_available():
        return ""

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    mime = "image/png"
    if img_bytes.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
    elif img_bytes.startswith(b"RIFF") and len(img_bytes) > 12 and img_bytes[8:12] == b"WEBP":
        mime = "image/webp"

    p_text = prompt or (
        "Read and extract ALL text from this image accurately. "
        "Preserve exact Vietnamese diacritics, letters, numbers, punctuation, and domain names. "
        "Return ONLY the extracted text, no explanations."
    )

    content_parts = [
        {"type": "text", "text": p_text},
        {
            "type": "file",
            "file": {
                "filename": f"ocr_image.{mime.split('/')[-1]}",
                "file_data": f"data:{mime};base64,{b64}"
            }
        }
    ]

    messages = [{"role": "user", "content": content_parts}]
    return _call_webai_chat(messages, timeout=15.0)


def resolve_quest_images_webai(image_bytes_list: List[bytes]) -> Dict[str, Any]:
    """
    Analyze Link4M shortlink mission screenshots via WebAI-to-API Gemini Vision.
    Extracts search keyword, target domain hint, and live domains.
    """
    if not image_bytes_list:
        return {}

    if not is_webai_available():
        return {}

    sorted_imgs = sorted([b for b in image_bytes_list if b and len(b) > 800], key=len, reverse=True)
    if not sorted_imgs:
        return {}

    prompt = (
        "Analyze these Vietnamese shortlink quest instructions and mission screenshots.\n"
        "Look carefully at all images, especially website headers, red arrows, red boxes, logos, and branding text.\n"
        "Extract the search instructions and return ONLY a valid JSON object with:\n"
        "- \"keyword\": The Google search query (e.g. \"keo nha cai\").\n"
        "- \"domain_hint\": The target domain or masked domain shown in text or logos (e.g. \"keobongda11.net\", \"soikeob***.live\").\n"
        "- \"target_domains\": Array of deduced exact live website domains from text, logos, or hints (e.g. [\"keobongda11.net\"]).\n"
        "- \"page_hint\": Target Google search page number (integer, default 1).\n"
        "Return ONLY raw JSON, no markdown, no other text."
    )

    content_parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]

    for idx, b in enumerate(sorted_imgs[:6]):
        mime = "image/png"
        if b.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        elif b.startswith(b"RIFF") and len(b) > 12 and b[8:12] == b"WEBP":
            mime = "image/webp"

        b64 = base64.b64encode(b).decode("utf-8")
        content_parts.append({
            "type": "file",
            "file": {
                "filename": f"mission_{idx}.{mime.split('/')[-1]}",
                "file_data": f"data:{mime};base64,{b64}"
            }
        })

    messages = [{"role": "user", "content": content_parts}]
    raw_res = _call_webai_chat(messages, timeout=35.0)
    if not raw_res:
        return {}

    data = _extract_json_from_text(raw_res)
    if isinstance(data, dict):
        return data

    # Fallback regex extraction
    kw_m = re.search(r'"keyword":\s*"([^"]+)"', raw_res)
    dh_m = re.search(r'"domain_hint":\s*"([^"]+)"', raw_res)
    res = {}
    if kw_m:
        res["keyword"] = kw_m.group(1)
    if dh_m:
        res["domain_hint"] = dh_m.group(1)
    return res
    return {}


def solve_math_captcha_webai(img_bytes: bytes, answers: List[Any]) -> Optional[Any]:
    """
    Solve math captcha from image using WebAI-to-API.
    Selects the matching answer from candidate list.
    """
    if not img_bytes or not answers:
        return None

    if not is_webai_available():
        return None

    ans_str = ", ".join(str(a) for a in answers)
    prompt = (
        f"Look at this math captcha image. Solve the mathematical expression.\n"
        f"Possible answer choices: [{ans_str}]\n"
        f"Return ONLY the exact matching answer value from the choices above. No words, no punctuation."
    )

    extracted = ocr_image_webai(img_bytes, prompt=prompt)
    if not extracted:
        return None

    # Check direct match in candidate answers
    for a in answers:
        if str(a) == extracted.strip():
            return a
        if re.search(rf"\b{re.escape(str(a))}\b", extracted):
            return a

    return None


def solve_recaptcha_v2_webai(img_bytes: bytes, instruction: Optional[str] = None, total_tiles: int = 9) -> List[int]:
    """
    Solve Google reCAPTCHA v2 image challenge using WebAI-to-API Gemini Vision.
    Returns 1-indexed list of tiles to click, e.g. [1, 5, 9].
    """
    if not img_bytes or len(img_bytes) < 100 or not is_webai_available():
        return []

    grid_desc = (
        "4x4 grid (16 tiles total, numbered 1 to 16: Row 1: 1-4, Row 2: 5-8, Row 3: 9-12, Row 4: 13-16)"
        if total_tiles == 16 else
        "3x3 grid (9 tiles total, numbered 1 to 9: Row 1: 1-3, Row 2: 4-6, Row 3: 7-9)"
    )

    inst_part = f"Target instruction: '{instruction}'" if instruction else "Detect the target instruction and object from the image header banner."
    prompt = (
        f"You are an expert AI Google reCAPTCHA v2 solver.\n"
        f"{inst_part}\n"
        f"Grid specification: {grid_desc}.\n"
        f"Identify which specific tile numbers contain the target object (even partially).\n"
        f"Return ONLY valid JSON: {{\"tiles\": [1, 2, ...]}} with integer tile numbers. If none, return {{\"tiles\": []}}."
    )

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    content_parts = [
        {"type": "text", "text": prompt},
        {
            "type": "file",
            "file": {
                "filename": "recaptcha_challenge.png",
                "file_data": f"data:image/png;base64,{b64}"
            }
        }
    ]

    raw_res = _call_webai_chat([{"role": "user", "content": content_parts}], timeout=45.0)
    if not raw_res:
        return []

    data = _extract_json_from_text(raw_res)
    if isinstance(data, dict):
        tiles = data.get("tiles") or data.get("tiles_to_click") or data.get("indices") or []
        if isinstance(tiles, list) and tiles:
            return [int(t) for t in tiles if 1 <= int(t) <= total_tiles]

    # Fallback regex: find array [ ... ]
    arr_m = re.search(r'\[(?:\s*\d+\s*,?)*\]', raw_res)
    if arr_m:
        try:
            arr = json.loads(arr_m.group(0))
            valid = [int(t) for t in arr if 1 <= int(t) <= total_tiles]
            if valid:
                return valid
        except Exception:
            pass

    return []


def solve_qcaptcha_webai(tile_bytes_list: List[bytes], question: str) -> List[int]:
    """
    Solve QCaptcha geometric tiles using WebAI-to-API Gemini Vision.
    Returns 0-indexed list of tiles (0 to 8).
    """
    if not tile_bytes_list or not is_webai_available():
        return []

    prompt = (
        f"You are an expert AI geometric captcha solver.\n"
        f"Question: \"{question}\"\n"
        f"There are {len(tile_bytes_list)} tiles shown in order from index 0 to {len(tile_bytes_list)-1}.\n"
        f"Determine which tile index (or indices) satisfy the question.\n"
        f"Return ONLY valid JSON: {{\"indices\": [0, 4]}} with integer indices."
    )

    content_parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for idx, b in enumerate(tile_bytes_list[:9]):
        if b:
            b64 = base64.b64encode(b).decode("utf-8")
            content_parts.append({
                "type": "file",
                "file": {
                    "filename": f"tile_{idx}.png",
                    "file_data": f"data:image/png;base64,{b64}"
                }
            })

    raw_res = _call_webai_chat([{"role": "user", "content": content_parts}], timeout=35.0)
    if not raw_res:
        return []

    data = _extract_json_from_text(raw_res)
    if isinstance(data, dict):
        indices = data.get("indices") or data.get("tiles") or []
        if isinstance(indices, list):
            return [int(i) for i in indices if 0 <= int(i) < len(tile_bytes_list)]

    return []
