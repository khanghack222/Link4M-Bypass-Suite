import os
import re
import time
import tempfile
import urllib.request
import json
import base64
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page, Locator

_env_key = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_KEY = _env_key if (_env_key and _env_key.startswith("AIzaSy")) else ""

class RecaptchaSolver:
    def __init__(self, headless: bool = True, **kwargs):
        self.headless = headless
        self._model = None
        self._faster_model = None

    @property
    def faster_model(self):
        if self._faster_model is None:
            try:
                import faster_whisper
                print("[*] Loading faster-whisper 'tiny.en' (CTranslate2 int8, ultra-light)...", flush=True)
                self._faster_model = faster_whisper.WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=2)
                print("[+] faster-whisper loaded.", flush=True)
            except Exception as e:
                self._faster_model = False
        return self._faster_model if self._faster_model is not False else None

    @property
    def model(self):
        if self._model is None:
            try:
                print("[*] Loading PyTorch Whisper 'tiny.en' fallback...", flush=True)
                import whisper
                self._model = whisper.load_model("tiny.en")
                print("[+] Whisper model loaded.", flush=True)
            except Exception:
                self._model = False
        return self._model if self._model is not False else None

    def transcribe_audio_url(self, audio_url: str) -> str:
        # Priority 0: API Client if available
        try:
            from captcha_api_client import solve_audio_recaptcha
            res_text = solve_audio_recaptcha(audio_url=audio_url)
            if res_text:
                return res_text.strip().lower()
        except Exception:
            pass

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp, open(tmp_path, "wb") as f:
                f.write(resp.read())

            # Priority 1: Google Speech Recognition (0 MB RAM, ultra fast ~300ms, ideal for low-spec hosting)
            try:
                import speech_recognition as sr
                import subprocess
                wav_path = tmp_path.replace(".mp3", ".wav")
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp_path, "-ac", "1", "-ar", "16000", wav_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
                if os.path.exists(wav_path):
                    try:
                        r = sr.Recognizer()
                        with sr.AudioFile(wav_path) as source:
                            audio_data = r.record(source)
                        text = r.recognize_google(audio_data, language="en-US")
                        clean = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip().lower()
                        if clean:
                            print(f"[+] Google SpeechRecognition solved audio: '{clean}' (0 RAM)", flush=True)
                            return clean
                    finally:
                        try: os.remove(wav_path)
                        except Exception: pass
            except Exception:
                pass

            # Priority 2: faster-whisper (CTranslate2 int8, no PyTorch, ~70MB RAM)
            if self.faster_model:
                try:
                    segments, _ = self.faster_model.transcribe(tmp_path, language="en")
                    raw = "".join(s.text for s in segments)
                    clean = re.sub(r'[^a-zA-Z0-9\s]', '', raw).strip().lower()
                    if clean:
                        print(f"[+] faster-whisper solved audio: '{clean}'", flush=True)
                        return clean
                except Exception:
                    pass

            # Priority 3: PyTorch Whisper fallback
            if self.model:
                res = self.model.transcribe(tmp_path, language="en", fp16=False)
                return re.sub(r'[^a-zA-Z0-9\s]', '', res.get("text", "")).strip().lower()

            return ""
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    def ask_gemini_vision_tiles(self, img_bytes: bytes, instruction: str, total_tiles: int = 9) -> List[int]:
        if not GEMINI_API_KEY:
            return []
        """Uses Gemini 3.1 Flash-Lite to solve reCAPTCHA v2 image challenge grids (3x3 or 4x4)."""
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        if total_tiles == 16:
            grid_spec = """This is a 4x4 grid (16 tiles total), numbered 1 to 16 from left to right, top to bottom:
Row 1: 1, 2, 3, 4
Row 2: 5, 6, 7, 8
Row 3: 9, 10, 11, 12
Row 4: 13, 14, 15, 16"""
        else:
            grid_spec = """This is a 3x3 grid (9 tiles total), numbered 1 to 9 from left to right, top to bottom:
Row 1: 1, 2, 3
Row 2: 4, 5, 6
Row 3: 7, 8, 9"""

        prompt = f"""You are an expert AI reCAPTCHA v2 solver.
Look at this Google reCAPTCHA image challenge screenshot.
Target instruction: "{instruction}"

Grid specification:
{grid_spec}

Identify all tile numbers (from 1 to {total_tiles}) that contain the requested target object (even partially).
If no tiles contain the target, return an empty list: {{"tiles": []}}.
Respond ONLY with a valid JSON:
{{"tiles": [1, 5, 9], "reason": "brief note"}}"""

        payload = json.dumps({
            "contents": [{
                "parts": [
                    {"inlineData": {"mimeType": "image/png", "data": b64_img}},
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0
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

    def solve_image_challenge(self, page: Page, active_bframe, chk, max_rounds: int = 20) -> bool:
        """Solves reCAPTCHA v2 image challenge using Gemini Vision directly inside Playwright bframe."""
        if not GEMINI_API_KEY:
            return False
        print("[*] Starting Multimodal Vision Image Solver for reCAPTCHA...", flush=True)
        for round_idx in range(max_rounds):
            if chk.get_attribute("aria-checked") == "true":
                return True

            try:
                active_bframe.locator(".rc-imageselect-instructions, .rc-imageselect-desc-no-canonical, .rc-imageselect-desc").first.wait_for(state="visible", timeout=4000)
            except Exception:
                pass

            header = active_bframe.locator(".rc-imageselect-instructions, .rc-imageselect-desc-no-canonical, .rc-imageselect-desc")
            if header.count() == 0:
                if chk.get_attribute("aria-checked") == "true":
                    return True
                # If still no image header, try clicking anchor checkbox to trigger image challenge
                try:
                    chk.click(force=True, timeout=2000)
                    time.sleep(1.5)
                    header = active_bframe.locator(".rc-imageselect-instructions, .rc-imageselect-desc-no-canonical, .rc-imageselect-desc")
                except Exception:
                    pass
                if header.count() == 0:
                    break
            instruction = header.first.inner_text().strip()
            print(f"[+] Vision Challenge Round {round_idx+1}: '{instruction.replace(chr(10), ' ')}'", flush=True)

            table_box = active_bframe.locator("table.rc-imageselect-table-33, table.rc-imageselect-table-44, .rc-imageselect-target table, .rc-imageselect-target")
            target_el = table_box.first if table_box.count() > 0 else challenge_box.first
            img_bytes = target_el.screenshot()

            tiles = active_bframe.locator("td.rc-imageselect-tile")
            total_tiles = tiles.count()
            tiles_to_click = self.ask_gemini_vision_tiles(img_bytes, instruction, total_tiles=total_tiles)

            if not tiles_to_click:
                is_skip = "click skip" in instruction.lower() or "if there are none" in instruction.lower()
                verify_btn = active_bframe.locator("#recaptcha-verify-button")
                if is_skip and verify_btn.is_visible():
                    verify_btn.click()
                    time.sleep(2.0)
                else:
                    # In a dynamic challenge or standard challenge without target, request fresh challenge via reload button
                    reload_btn = active_bframe.locator("#recaptcha-reload-button")
                    if reload_btn.is_visible():
                        reload_btn.click(force=True)
                        time.sleep(2.0)
                    elif verify_btn.is_visible():
                        verify_btn.click()
                        time.sleep(2.0)

                if chk.get_attribute("aria-checked") == "true":
                    return True
                continue

            is_dynamic = "none left" in instruction.lower() or "once there are none" in instruction.lower()
            if is_dynamic:
                dyn_rounds = 0
                while tiles_to_click and dyn_rounds < 8:
                    dyn_rounds += 1
                    for idx in tiles_to_click:
                        if 1 <= idx <= total_tiles:
                            tile = tiles.nth(idx - 1)
                            tile.click(force=True)
                            time.sleep(0.3)
                    # Chờ hoạt ảnh làm mờ và load ảnh mới hoàn toàn (4.2s)
                    time.sleep(4.2)
                    img_bytes = target_el.screenshot()
                    tiles_to_click = self.ask_gemini_vision_tiles(img_bytes, instruction, total_tiles=total_tiles)
                    if not tiles_to_click:
                        break
            else:
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
                time.sleep(2.5)

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

                # --- STEP 1: Attempt Multimodal Vision Image Challenge FIRST if available ---
                solved = False
                has_visual = active_bframe.locator(".rc-imageselect-instructions, .rc-imageselect-desc, .rc-imageselect-desc-no-canonical, .rc-imageselect").count() > 0
                if has_visual:
                    print("[+] Visual challenge already presented. Solving via Gemini Multimodal Vision...", flush=True)
                    solved = self.solve_image_challenge(page, active_bframe, chk)

                # --- STEP 2: Fallback to Audio Challenge if visual not present or failed ---
                if not solved and chk.get_attribute("aria-checked") != "true":
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
                            print("[!] Audio challenge unavailable or rate-limited by Google ('Try again later'). Fallback to Visual Solver...", flush=True)
                            # Kiểm tra nếu bị Google Rate Limit (doscaptcha header xuất hiện)
                            is_doscaptcha = active_bframe.locator(".rc-doscaptcha-header-text, .rc-audiochallenge-error-message").count() > 0
                            if is_doscaptcha:
                                print("[!] Google DOSCAPTCHA rate limit confirmed on current IP. Switching automatically to Visual Image Solver...", flush=True)

                # --- STEP 3: Fallback back to Visual Challenge if still not solved ---
                if not solved and chk.get_attribute("aria-checked") != "true":
                    try:
                        image_btn = active_bframe.locator("#recaptcha-image-button")
                        reload_btn = active_bframe.locator("#recaptcha-reload-button")
                        if image_btn.count() > 0 and image_btn.is_visible():
                            image_btn.click(force=True, timeout=2000)
                            time.sleep(1.5)
                        elif reload_btn.count() > 0 and reload_btn.is_visible() and not active_bframe.locator(".rc-imageselect").is_visible():
                            btn_class = reload_btn.get_attribute("class") or ""
                            if "rc-button-disabled" not in btn_class and not reload_btn.get_attribute("disabled"):
                                reload_btn.click(force=True, timeout=2000)
                                time.sleep(1.5)
                    except Exception:
                        pass

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
get_solver_instance = get_solver

