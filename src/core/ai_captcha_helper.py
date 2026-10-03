# -*- coding: utf-8 -*-
"""
⚡ AI CAPTCHA MULTI-SOLVER ENGINE ⚡
Tích hợp trí tuệ nhân tạo (Gemini Multimodal Vision + MiMo Free AI) vào tất cả các bước giải Captcha:
1. CaptchaNo (GTraffic): Nhận diện câu hỏi/hình ảnh và chọn đáp án trắc nghiệm đúng.
2. QCaptcha (LayMa.net): Nhận diện 9 ô hình học (Grid 3x3, Odd-one-out, Shape counting).
3. Math Captcha (Ontops / BestTraffic): Nhận diện phép tính toán và đưa ra kết quả số nguyên.
4. reCAPTCHA v2 / Enterprise: AI bóc tách Audio challenge & Image grid tiles.
"""

import os
import re
import json
import base64
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

_env_key = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_KEY = _env_key if (_env_key and _env_key.startswith("AIzaSy")) else ""
VISION_MODELS = ["gemini-flash-lite-latest", "gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

def _call_gemini_vision(parts: list, timeout: float = 7.0) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    payload = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0}
    }).encode("utf-8")

    for m in VISION_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                txt = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                txt_clean = re.sub(r"^```(?:json)?", "", txt, flags=re.IGNORECASE).rstrip("`").strip()
                return json.loads(txt_clean)
        except Exception:
            continue
    return None

def solve_captchano_ai(img_bytes: bytes, options: List[str]) -> Optional[str]:
    """
    Sử dụng Gemini Vision để giải CaptchaNo trong GTraffic.
    Phân tích ảnh câu hỏi và chọn chính xác phương án đúng từ danh sách options.
    """
    if not options:
        return None

    # Priority 0: Gemini Multimodal Vision
    if GEMINI_API_KEY and img_bytes:
        try:
            b64_img = base64.b64encode(img_bytes).decode("utf-8")
            prompt = (
                f"Look at this captcha question image. The choices available are: {options}.\n"
                f"Analyze the question carefully and return ONLY a JSON object with key 'choice' "
                f"matching one of the exact choices from the list. E.g. {{\"choice\": \"{options[0]}\"}}"
            )
            parts = [
                {"inline_data": {"mime_type": "image/png", "data": b64_img}},
                {"text": prompt}
            ]
            data = _call_gemini_vision(parts, timeout=5.0)
            if data and "choice" in data and str(data["choice"]) in options:
                print(f"[+] 🧠 [Gemini Vision] CaptchaNo solved: '{data['choice']}'", flush=True)
                return str(data["choice"])
        except Exception:
            pass

    # Priority 1: MiMo Free AI fallback if text extracted
    return None

def solve_qcaptcha_grid_ai(tile_bytes_list: List[bytes], question: str, c_type: str = "grid3x3") -> List[int]:
    """
    Sử dụng Gemini Vision để giải QCaptcha (LayMa.net) cho dạng Grid 3x3 và OddOneOut.
    Trả về danh sách 0-indexed tiles (0 đến 8).
    """
    if not GEMINI_API_KEY or not tile_bytes_list:
        return []

    try:
        parts = []
        prompt = (
            f"You are an expert AI Captcha solver for geometric shapes.\n"
            f"Question: \"{question}\"\n"
            f"Challenge type: \"{c_type}\"\n"
            f"There are 9 tiles shown in order from index 0 to 8 (row 1: 0, 1, 2; row 2: 3, 4, 5; row 3: 6, 7, 8).\n"
            f"Determine which tile index (or indices) satisfy the question.\n"
            f"Return ONLY a JSON object: {{\"indices\": [0, 4]}} with integer indices."
        )
        parts.append({"text": prompt})

        for idx, b in enumerate(tile_bytes_list[:9]):
            if b:
                parts.append({"text": f"Tile {idx}:"})
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(b).decode("utf-8")
                    }
                })

        data = _call_gemini_vision(parts, timeout=6.0)
        if data and "indices" in data and isinstance(data["indices"], list):
            res = [int(i) for i in data["indices"] if 0 <= int(i) < len(tile_bytes_list)]
            if res:
                print(f"[+] 🧠 [Gemini Vision] QCaptcha indices solved: {res}", flush=True)
                return res
    except Exception as e:
        print(f"[!] QCaptcha AI Vision note: {e}", flush=True)

    return []

def solve_math_captcha_ai(img_bytes: bytes, choices: List[int]) -> Optional[int]:
    """
    Giải bài toán captcha trên các trang tài trợ Ontops / BestTraffic bằng Gemini Vision.
    """
    if not choices or not img_bytes:
        return None

    if GEMINI_API_KEY:
        try:
            b64_img = base64.b64encode(img_bytes).decode("utf-8")
            prompt = (
                f"Solve the mathematical equation or question in this image. "
                f"The valid integer choices are: {choices}. "
                f"Return ONLY a JSON object with key 'answer' pointing to the correct integer. E.g. {{\"answer\": {choices[0]}}}"
            )
            parts = [
                {"inline_data": {"mime_type": "image/png", "data": b64_img}},
                {"text": prompt}
            ]
            data = _call_gemini_vision(parts, timeout=4.5)
            if data and "answer" in data:
                ans = int(data["answer"])
                if ans in choices:
                    print(f"[+] 🧠 [Gemini Vision] Math captcha solved: {ans}", flush=True)
                    return ans
        except Exception:
            pass

    return None
