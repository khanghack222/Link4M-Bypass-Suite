import requests
import json
import time
import subprocess
import os

OPENCODE_SERVE_PORT = 50123
OPENCODE_SERVE_URL = f"http://127.0.0.1:{OPENCODE_SERVE_PORT}"

def ensure_opencode_daemon() -> bool:
    """Đảm bảo OpenCode daemon luôn chạy ở cổng 50123."""
    try:
        r = requests.get(f"{OPENCODE_SERVE_URL}/session", timeout=1.5)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    try:
        opencode_bin = "opencode.cmd" if os.name == "nt" else "opencode"
        subprocess.Popen(
            [opencode_bin, "serve", "--port", str(OPENCODE_SERVE_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=(os.name == "nt"),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
        for _ in range(10):
            time.sleep(0.5)
            try:
                r = requests.get(f"{OPENCODE_SERVE_URL}/session", timeout=1.5)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False

def ask_mimo_free(prompt_text: str, model_id: str = "mimo-v2.6-flash-free") -> str:
    """
    Reverse bypass OpenCode server để gọi trực tiếp model MiMo Free hoàn toàn miễn phí.
    """
    try:
        ensure_opencode_daemon()
        # 1. Tạo session phiên làm việc
        s_resp = requests.post(f"{OPENCODE_SERVE_URL}/session", json={"title": "Captcha Solver Session"}, timeout=5)
        if s_resp.status_code != 200:
            return ""
        session_id = s_resp.json().get("id")
        if not session_id:
            return ""

        # 2. Gửi message đồng bộ nhận phản hồi trực tiếp từ model
        payload = {
            "model": {
                "providerID": "opencode",
                "modelID": model_id
            },
            "parts": [
                {"type": "text", "text": prompt_text}
            ]
        }
        m_resp = requests.post(f"{OPENCODE_SERVE_URL}/session/{session_id}/message", json=payload, timeout=25)
        if m_resp.status_code != 200:
            return ""

        data = m_resp.json()
        parts = data.get("parts", [])
        result_text = ""
        for p in parts:
            if p.get("type") == "text":
                result_text = p.get("text", "").strip()
                break

        # Delete session to keep daemon state lightweight
        try:
            requests.delete(f"{OPENCODE_SERVE_URL}/session/{session_id}", timeout=2)
        except Exception:
            pass

        return result_text
    except Exception as e:
        pass
    return ""

if __name__ == "__main__":
    t0 = time.time()
    ans = ask_mimo_free("Solve math: 100 * 25 = ? Return ONLY the exact number.")
    print(f"MiMo Free Answer: {ans} (in {round(time.time() - t0, 2)}s)")
