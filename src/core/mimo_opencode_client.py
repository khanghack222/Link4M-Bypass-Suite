import requests
import json
import time
import subprocess
import os
import random
import uuid
import base64
from typing import List, Optional

OPENCODE_SERVE_PORT = 50123
OPENCODE_SERVE_URL = f"http://127.0.0.1:{OPENCODE_SERVE_PORT}"

# Session cục bộ không bị ảnh hưởng bởi biến môi trường HTTP_PROXY / HTTPS_PROXY
_LOCAL_SESSION = requests.Session()
_LOCAL_SESSION.trust_env = False

# Cache for proxies loaded from proxies.txt
_PROXY_CACHE = []
_LAST_PROXY_LOAD = 0

def load_proxies() -> List[str]:
    global _PROXY_CACHE, _LAST_PROXY_LOAD
    now = time.time()
    if _PROXY_CACHE and (now - _LAST_PROXY_LOAD < 300):
        return _PROXY_CACHE

    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "proxies.txt"),
        os.path.join(os.getcwd(), "proxies.txt"),
        r"C:\Users\XUAN\.gemini\antigravity\scratch\Link4M_Bypass_Suite\proxies.txt"
    ]
    loaded = []
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip().lstrip("\ufeff")
                        if line and not line.startswith("#"):
                            loaded.append(line)
                if loaded:
                    break
            except Exception:
                pass
    _PROXY_CACHE = loaded
    _LAST_PROXY_LOAD = now
    return _PROXY_CACHE

def get_random_device_id() -> str:
    """Tạo Device ID ngẫu nhiên để chống rate-limit trên mỗi thiết bị."""
    return str(uuid.uuid4())

def ensure_opencode_daemon() -> bool:
    """Đảm bảo OpenCode daemon luôn chạy ở cổng 50123 với chế độ --pure và kết nối qua ProxyRotatorBridge."""
    # Khởi động ProxyRotatorBridge nếu có file proxies.txt
    try:
        try:
            from proxy_rotator import ensure_proxy_rotator_bridge, LOCAL_BRIDGE_HOST, LOCAL_BRIDGE_PORT
        except ImportError:
            from src.core.proxy_rotator import ensure_proxy_rotator_bridge, LOCAL_BRIDGE_HOST, LOCAL_BRIDGE_PORT
        ensure_proxy_rotator_bridge()
    except Exception:
        pass

    try:
        r = _LOCAL_SESSION.get(f"{OPENCODE_SERVE_URL}/session", timeout=1.5)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    try:
        opencode_bin = r"C:\Users\XUAN\AppData\Roaming\npm\opencode.cmd"
        if not os.path.exists(opencode_bin):
            opencode_bin = "opencode.cmd" if os.name == "nt" else "opencode"

        env = os.environ.copy()
        # Ép OpenCode daemon đi qua proxy bridge 127.0.0.1:18888 để tự động xoay IP residential
        bridge_proxy_url = "http://127.0.0.1:18888"
        env["HTTP_PROXY"] = bridge_proxy_url
        env["HTTPS_PROXY"] = bridge_proxy_url
        env["http_proxy"] = bridge_proxy_url
        env["https_proxy"] = bridge_proxy_url
        env["NO_PROXY"] = "localhost,127.0.0.1"

        # Chạy sạch không bị vướng plugin nặng (--pure)
        subprocess.Popen(
            [opencode_bin, "serve", "--port", str(OPENCODE_SERVE_PORT), "--pure"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            shell=(os.name == "nt"),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
        for _ in range(14):
            time.sleep(0.5)
            try:
                r = _LOCAL_SESSION.get(f"{OPENCODE_SERVE_URL}/session", timeout=1.5)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False

def _call_mimo_raw(parts: list, model_id: str = "mimo-v2.6-flash-free", max_wait: float = 25.0) -> str:
    """
    Gửi câu lệnh tới OpenCode daemon qua cơ chế prompt_async + polling.
    Hỗ trợ fake Device ID, Session isolation và tránh timeout của HTTP POST synchronous.
    """
    if not ensure_opencode_daemon():
        return ""

    device_id = get_random_device_id()
    session_title = f"AI_{device_id[:8]}"

    try:
        # 1. Tạo session mới
        s_resp = _LOCAL_SESSION.post(
            f"{OPENCODE_SERVE_URL}/session",
            json={"title": session_title},
            headers={"x-opencode-device-id": device_id},
            timeout=4.0
        )
        if s_resp.status_code != 200:
            return ""

        session_id = s_resp.json().get("id")
        if not session_id:
            return ""

        # 2. Gửi prompt_async (trả về 204 No Content tức thì, không bị chặn IO timeout)
        payload = {
            "model": {
                "providerID": "opencode",
                "modelID": model_id
            },
            "parts": parts
        }
        headers = {
            "x-opencode-device-id": device_id,
            "x-client-device-id": device_id
        }

        async_resp = _LOCAL_SESSION.post(
            f"{OPENCODE_SERVE_URL}/session/{session_id}/prompt_async",
            json=payload,
            headers=headers,
            timeout=5.0
        )
        if async_resp.status_code not in (200, 204):
            return ""

        # 3. Polling nhận kết quả từ assistant
        t_start = time.time()
        while time.time() - t_start < max_wait:
            time.sleep(0.8)
            try:
                msg_resp = _LOCAL_SESSION.get(f"{OPENCODE_SERVE_URL}/session/{session_id}/message", timeout=3.5)
                if msg_resp.status_code != 200:
                    continue
                msgs = msg_resp.json()
                for m in msgs:
                    if m.get("info", {}).get("role") == "assistant":
                        # Trích xuất phần phản hồi text
                        for p in m.get("parts", []):
                            if p.get("type") == "text" and p.get("text", "").strip():
                                ans = p.get("text", "").strip()
                                # Dọn dẹp session
                                try:
                                    _LOCAL_SESSION.delete(f"{OPENCODE_SERVE_URL}/session/{session_id}", timeout=1.5)
                                except Exception:
                                    pass
                                return ans
            except Exception:
                pass

        # Timeout dọn dẹp
        try:
            _LOCAL_SESSION.delete(f"{OPENCODE_SERVE_URL}/session/{session_id}", timeout=1.5)
        except Exception:
            pass

    except Exception:
        pass
    return ""

def ask_mimo_free(prompt_text: str, model_id: str = "mimo-v2.6-flash-free") -> str:
    """Gọi model MiMo Free xử lý prompt văn bản (toán, domain unmask, logic)."""
    parts = [{"type": "text", "text": prompt_text}]
    res = _call_mimo_raw(parts, model_id=model_id, max_wait=30.0)
    if not res and model_id != "mimo-v2.5-free":
        # Fallback sang mimo-v2.5-free nếu v2.6 bận
        res = _call_mimo_raw(parts, model_id="mimo-v2.5-free", max_wait=25.0)
    return res

def ask_mimo_vision_tiles(img_bytes: bytes, instruction: str, total_tiles: int = 9) -> List[int]:
    """
    Gọi model MiMo Multimodal Vision qua file Data-URI để giải reCAPTCHA v2 dạng ảnh.
    Trả về danh sách ô (1-indexed) chính xác.
    """
    try:
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64_img}"

        if total_tiles == 16:
            grid_desc = "4x4 grid (16 tiles total, numbered 1 to 16 from left to right, top to bottom)."
        else:
            grid_desc = "3x3 grid (9 tiles total, numbered 1 to 9 from left to right, top to bottom)."

        prompt = (
            f"You are an expert AI reCAPTCHA v2 solver.\n"
            f"Target instruction: '{instruction}'\n"
            f"Grid layout: {grid_desc}\n"
            f"Identify all tile numbers (from 1 to {total_tiles}) that contain the requested object.\n"
            f"Return ONLY a JSON array of integers, e.g. [1, 5, 9]. If none, return []."
        )

        parts = [
            {"type": "file", "mime": "image/png", "url": data_uri},
            {"type": "text", "text": prompt}
        ]

        raw = _call_mimo_raw(parts, model_id="mimo-v2.6-flash-free", max_wait=25.0)
        if not raw:
            return []

        # Parse JSON array từ kết quả
        import re
        m = re.search(r'\[(?:\s*\d+\s*,?)*\]', raw)
        if m:
            tiles = json.loads(m.group(0))
            valid = [int(t) for t in tiles if 1 <= int(t) <= total_tiles]
            return valid

        # Fallback regex số
        digits = [int(d) for d in re.findall(r'\b\d+\b', raw) if 1 <= int(d) <= total_tiles]
        return digits[:6]
    except Exception:
        return []

def ocr_image_mimo(img_bytes: bytes) -> str:
    """
    Sử dụng model MiMo Multimodal Vision (100% Free qua OpenCode daemon)
    để đọc văn bản tiếng Việt/tiếng Anh trong ảnh nhiệm vụ Link4M với độ chính xác tuyệt đối.
    """
    try:
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64_img}"
        prompt = "Read all text in this image accurately. Return ONLY the exact text found in the image in Vietnamese or English. No markdown, no explanations."
        parts = [
            {"type": "file", "mime": "image/png", "url": data_uri},
            {"type": "text", "text": prompt}
        ]
        raw = _call_mimo_raw(parts, model_id="mimo-v2.6-flash-free", max_wait=25.0)
        return raw.strip() if raw else ""
    except Exception:
        return ""

if __name__ == "__main__":
    t0 = time.time()
    ans = ask_mimo_free("Solve math: 100 * 25 = ? Return ONLY the exact number.")
    print(f"MiMo Free Answer: {ans} (in {round(time.time() - t0, 2)}s)")
