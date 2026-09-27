import os
import re
import time
import tempfile
import urllib.request
import json
import base64
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page, Locator

_DEFAULT_GEMINI_KEY = "AQ.Ab8RN6K2TKrVe2p7DR5t65zPs75m2AU_MSTHQUr2o-oWXt9gug"
_env_key = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_KEY = _env_key if (_env_key and not _env_key.startswith("sk-")) else _DEFAULT_GEMINI_KEY

class RecaptchaSolver:
    def __init__(self, headless: bool = True, **kwargs):
        self.headless = headless
        self._model = None

    @property
    def model(self):
        if self._model is None:
            print("[*] Loading Whisper 'tiny.en' (ultra-fast cached)...", flush=True)
            import whisper
            self._model = whisper.load_model("tiny.en")
            print("[+] Whisper model loaded.", flush=True)
        return self._model

    def transcribe_audio_url(self, audio_url: str) -> str:
        # Priority 0: API Client if available
        try:
            from captcha_api_client import solve_audio_recaptcha
            res_text = solve_audio_recaptcha(audio_url=audio_url)
            if res_text:
                return res_text.strip().lower()
        except Exception:
            pass

        # Priority 1: Local Whisper
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp, open(tmp_path, "wb") as f:
                f.write(resp.read())
            res = self.model.transcribe(tmp_path, language="en", fp16=False)
            return re.sub(r'[^a-zA-Z0-9\s]', '', res.get("text", "")).strip().lower()
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    def ask_gemini_vision_tiles(self, img_bytes: bytes, instruction: str) -> List[int]:
        """Uses Gemini 3.1 Flash-Lite to solve reCAPTCHA v2 image challenge grids (3x3 or 4x4)."""
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        prompt = f"""You are an expert AI reCAPTCHA solver.
Look at this Google reCAPTCHA v2 image challenge screenshot.
The instruction is: "{instruction}"

Carefully note the grid size:
- If 3x3 (9 tiles), numbered left-to-right, top-to-bottom:
  Row 1: 1, 2, 3
  Row 2: 4, 5, 6
  Row 3: 7, 8, 9

- If 4x4 (16 tiles), numbered left-to-right, top-to-bottom:
  Row 1: 1, 2, 3, 4
  Row 2: 5, 6, 7, 8
  Row 3: 9, 10, 11, 12
  Row 4: 13, 14, 15, 16

Identify all tile numbers that clearly contain the requested object (even partially).
Respond ONLY with a valid JSON object in this format:
{{"tiles": [1, 5, 9], "reason": "brief note"}}
"""
        payload = json.dumps({
            "contents": [{
                "parts": [
                    {"inlineData": {"mimeType": "image/png", "data": b64_img}},
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }).encode("utf-8")

        models = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
        for m in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=9.0) as r:
                    res = json.loads(r.read().decode("utf-8"))
                    txt = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                    txt = re.sub(r"^```(?:json)?", "", txt, flags=re.IGNORECASE).rstrip("`").strip()
                    data = json.loads(txt)
                    tiles = data.get("tiles", [])
                    print(f"[+] [Gemini Vision {m}] Identified reCAPTCHA tiles: {tiles} ({data.get('reason', '')})", flush=True)
                    return tiles
            except Exception as e:
                pass
        return []

    def solve_image_challenge(self, page: Page, active_bframe, chk, max_rounds: int = 8) -> bool:
        """Solves reCAPTCHA v2 image challenge using Gemini Vision directly inside Playwright bframe."""
        print("[*] Starting Multimodal Vision Image Solver for reCAPTCHA...", flush=True)
        for round_idx in range(max_rounds):
            if chk.get_attribute("aria-checked") == "true":
                return True

            time.sleep(1.0)
            header = active_bframe.locator(".rc-imageselect-instructions, .rc-imageselect-desc-no-canonical, .rc-imageselect-desc")
            if header.count() == 0:
                if chk.get_attribute("aria-checked") == "true":
                    return True
                break
            instruction = header.first.inner_text().strip()
            print(f"[+] Vision Challenge Round {round_idx+1}: '{instruction.replace(chr(10), ' ')}'", flush=True)

            challenge_box = active_bframe.locator(".rc-imageselect, #rc-imageselect")
            if challenge_box.count() == 0:
                break
            img_bytes = challenge_box.first.screenshot()

            tiles_to_click = self.ask_gemini_vision_tiles(img_bytes, instruction)
            tiles = active_bframe.locator("td.rc-imageselect-tile")
            total_tiles = tiles.count()

            if not tiles_to_click:
                verify_btn = active_bframe.locator("#recaptcha-verify-button")
                if verify_btn.is_visible():
                    verify_btn.click()
                    time.sleep(2.0)
                if chk.get_attribute("aria-checked") == "true":
                    return True
                continue

            for idx in tiles_to_click:
                if 1 <= idx <= total_tiles:
                    tile = tiles.nth(idx - 1)
                    tile.scroll_into_view_if_needed()
                    tile.click(force=True)
                    time.sleep(0.3)

            time.sleep(0.8)
            verify_btn = active_bframe.locator("#recaptcha-verify-button")
            if verify_btn.is_visible():
                btn_txt = verify_btn.inner_text().strip()
                print(f"[+] Clicking challenge button: '{btn_txt}'", flush=True)
                verify_btn.click()
                time.sleep(2.2)

            if chk.get_attribute("aria-checked") == "true":
                return True

        return chk.get_attribute("aria-checked") == "true"

    def _sync_tokens(self, page: Page, token: str):
        if not token:
            return
        page.evaluate("""(tok) => {
            document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
                el.value = tok;
            });
        }""", token)

    def solve_on_page(self, page: Page, timeout_sec: int = 40, container_selector: str = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        
        # Build strict target CSS without selector bleeding
        if container_selector:
            parts = [s.strip() for s in container_selector.split(",") if s.strip()]
            target_css = ", ".join([f"{p} iframe[src*='recaptcha/api2/anchor'], {p} iframe[src*='recaptcha/enterprise/anchor']" for p in parts])
        else:
            target_css = "iframe[src*='recaptcha/api2/anchor'], iframe[src*='recaptcha/enterprise/anchor']"

        candidate_anchors = []
        for _wait in range(20):
            anchors = page.locator(target_css).all()
            for idx, a in enumerate(anchors):
                try:
                    box = a.bounding_box()
                    if not box or box.get('height', 0) < 30 or box.get('width', 0) < 100:
                        continue
                    cf = a.content_frame
                    if not cf:
                        continue
                    chk = cf.locator("#recaptcha-anchor")
                    if chk.count() == 0:
                        continue
                    
                    body_text = cf.locator("body").inner_text() or ""
                    has_quota_error = any(w in body_text.lower() for w in ["quota", "exceeding", "bị lỗi", "error"])
                    
                    y_pos = box['y'] if box else 0
                    
                    # Detect if anchor is inside form
                    is_in_main = False
                    try:
                        is_in_main = a.evaluate("el => el.closest('#main-form') !== null")
                    except Exception:
                        pass
                    
                    candidate_anchors.append({
                        "anchor": a,
                        "frame": cf,
                        "chk": chk,
                        "y": y_pos,
                        "has_error": has_quota_error,
                        "is_in_main": is_in_main,
                        "index": idx
                    })
                except Exception:
                    continue
            if candidate_anchors:
                break
            time.sleep(0.4)

        if not candidate_anchors:
            return {"success": False, "error": "no_anchors_found"}

        # Sort: healthy first, #main-form first, then top-most
        candidate_anchors.sort(key=lambda x: (not x["has_error"], 1 if x["is_in_main"] else 0, -x["y"]), reverse=True)

        for cand in candidate_anchors:
            try:
                a = cand["anchor"]
                chk = cand["chk"]
                cf = cand["frame"]
                
                try:
                    a.scroll_into_view_if_needed()
                    time.sleep(0.3)
                except Exception:
                    pass

                try:
                    chk.click(force=True, timeout=4000)
                except Exception:
                    try:
                        cf.locator("#recaptcha-anchor").click(force=True, timeout=2000)
                    except Exception:
                        pass
                time.sleep(2.0)

                # Check for instant solve
                if chk.get_attribute("aria-checked") == "true":
                    token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                    elapsed = round((time.perf_counter() - t0) * 1000, 2)
                    print(f"[+] Instantly solved without challenge in {elapsed}ms!", flush=True)
                    self._sync_tokens(page, token)
                    return {"success": True, "token": token, "type": "instant", "time_ms": elapsed}

                # Deterministic 1-to-1 matching: Anchor name a-XXXX maps exactly to bframe c-XXXX
                active_bframe = None
                a_name = a.get_attribute("name") or ""
                target_bname = "c-" + a_name[2:] if a_name.startswith("a-") else None

                for _ in range(25):
                    if target_bname:
                        direct_bf = page.locator(f"iframe[name='{target_bname}']")
                        if direct_bf.count() > 0:
                            cf_candidate = direct_bf.first.content_frame
                            if cf_candidate and cf_candidate.locator("#recaptcha-audio-button, .rc-imageselect, #recaptcha-verify-button").count() > 0:
                                active_bframe = cf_candidate
                                break

                    # Secondary: check all bframes on page
                    bframes = page.locator("iframe[src*='recaptcha/api2/bframe'], iframe[src*='recaptcha/enterprise/bframe']").all()
                    for bf in bframes:
                        try:
                            b_cf = bf.content_frame
                            if b_cf and b_cf.locator("#recaptcha-audio-button, #recaptcha-verify-button, .rc-imageselect, .rc-doscaptcha-header-text").count() > 0:
                                active_bframe = b_cf
                                break
                        except Exception:
                            pass
                    if active_bframe:
                        break
                    time.sleep(0.3)

                if not active_bframe:
                    print(f"[!] No visible bframe for candidate anchor {cand['index']}. Trying next candidate...", flush=True)
                    continue

                # --- STEP 1: Attempt Audio Challenge ---
                audio_btn = active_bframe.locator("#recaptcha-audio-button")
                audio_allowed = False
                if audio_btn.count() > 0:
                    btn_class = audio_btn.get_attribute("class") or ""
                    if "rc-button-disabled" not in btn_class and not audio_btn.get_attribute("disabled"):
                        try:
                            audio_btn.scroll_into_view_if_needed()
                            audio_btn.click(force=True, timeout=2500)
                            audio_allowed = True
                            print("[+] Audio challenge requested!", flush=True)
                        except Exception:
                            pass

                solved = False
                if audio_allowed:
                    time.sleep(1.5)
                    download_link = active_bframe.locator(".rc-audiochallenge-tdownload-link, a:has-text('Download')")
                    try:
                        download_link.wait_for(state="visible", timeout=6000)
                        audio_url = download_link.get_attribute("href")
                    except Exception:
                        audio_url = None

                    if audio_url:
                        ans = self.transcribe_audio_url(audio_url)
                        print(f"[+] Audio answer: '{ans}'", flush=True)
                        input_field = active_bframe.locator("#audio-response")
                        input_field.fill(ans)
                        active_bframe.locator("#recaptcha-verify-button").click()
                        time.sleep(2.0)

                        if chk.get_attribute("aria-checked") == "true":
                            solved = True
                    else:
                        print("[!] Audio challenge unavailable or rate-limited by Google ('Try again later').", flush=True)

                # --- STEP 2: Fallback to Multimodal Vision Image Solver ---
                if not solved and chk.get_attribute("aria-checked") != "true":
                    # If audio failed, reload or switch to image mode if needed
                    reload_btn = active_bframe.locator("#recaptcha-reload-button")
                    image_btn = active_bframe.locator("#recaptcha-image-button")
                    if image_btn.is_visible():
                        image_btn.click(force=True)
                        time.sleep(1.5)
                    elif reload_btn.is_visible() and not active_bframe.locator(".rc-imageselect").is_visible():
                        reload_btn.click(force=True)
                        time.sleep(1.5)

                    solved = self.solve_image_challenge(page, active_bframe, chk)

                if solved or chk.get_attribute("aria-checked") == "true":
                    token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                    elapsed = round((time.perf_counter() - t0) * 1000, 2)
                    print(f"[+] reCAPTCHA solved successfully in {elapsed}ms!", flush=True)
                    self._sync_tokens(page, token)
                    return {"success": True, "token": token, "type": "solved", "time_ms": elapsed}

            except Exception as e:
                print(f"[!] Error on candidate {cand['index']}: {e}", flush=True)
                continue

        return {"success": False, "error": "all_candidates_failed"}


_SOLVER_INSTANCE = None

def get_solver(headless: bool = True, **kwargs) -> RecaptchaSolver:
    global _SOLVER_INSTANCE
    if _SOLVER_INSTANCE is None:
        _SOLVER_INSTANCE = RecaptchaSolver(headless=headless, **kwargs)
    return _SOLVER_INSTANCE

RecaptchaAudioSolver = RecaptchaSolver


