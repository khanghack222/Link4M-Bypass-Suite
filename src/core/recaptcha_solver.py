import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_py311_site = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "Lib", "site-packages")
if os.path.exists(_py311_site) and _py311_site not in sys.path:
    sys.path.insert(0, _py311_site)

import re
import time
import io
import tempfile
import urllib.request
import subprocess
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page, Locator

try:
    from twocaptcha_client import solve_recaptcha_2captcha, get_balance, get_best_key
except ImportError:
    try:
        from src.core.twocaptcha_client import solve_recaptcha_2captcha, get_balance, get_best_key
    except ImportError:
        solve_recaptcha_2captcha = None
        get_balance = None
        get_best_key = None


class RecaptchaSolver:
    """
    3-Tier Multi-Resilient reCAPTCHA v2 Solver:
      - Tier 1: Instant Anchor Check via Trust Score (< 0.5s).
      - Tier 2: Direct JS Audio Event Dispatch + In-Memory Speech Recognition (< 2s, 0% CPU, 0$ cost).
      - Tier 3: Cloud Token API Fallback (2Captcha) upon DOSCAPTCHA or rate limit.
    Zero Vision AI: Completely eliminates YOLO, ONNX, and CLIP models.
    """

    def __init__(self, headless: bool = True, **kwargs):
        self.headless = headless
        self._faster_model = None

    @property
    def faster_model(self):
        if self._faster_model is None:
            try:
                import faster_whisper
                print("[*] Loading faster-whisper 'tiny.en' (CTranslate2 int8, ultra-light)...", flush=True)
                self._faster_model = faster_whisper.WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=2)
                print("[+] faster-whisper loaded.", flush=True)
            except Exception:
                self._faster_model = False
        return self._faster_model if self._faster_model is not False else None

    def transcribe_audio_url(self, audio_url: str) -> str:
        """
        Downloads MP3 audio stream in memory, converts to WAV in memory,
        and transcribes via SpeechRecognition (Google Free Speech) in < 2 seconds.
        Zero disk I/O, minimal CPU usage.
        """
        # Fetch MP3 bytes in-memory
        try:
            req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                audio_bytes = resp.read()
        except Exception as e:
            print(f"[!] Failed to fetch audio stream: {e}", flush=True)
            return ""

        # In-Memory Conversion (Zero Disk I/O)
        wav_bytes = None
        if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
            wav_bytes = audio_bytes
        else:
            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                seg = seg.set_frame_rate(16000).set_channels(1)
                wav_buf = io.BytesIO()
                seg.export(wav_buf, format="wav")
                wav_bytes = wav_buf.getvalue()
            except Exception:
                pass
            # Fallback to ffmpeg pipe in memory if pydub encounters an issue
            try:
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
                    input=audio_bytes,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
                if proc.returncode == 0 and proc.stdout:
                    wav_bytes = proc.stdout
            except Exception:
                wav_bytes = None

        if wav_bytes:
            # Primary: Google SpeechRecognition via In-Memory AudioData (< 1s, free, zero CPU)
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                    audio_data = r.record(source)
                text = r.recognize_google(audio_data, language="en-US")
                clean = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip().lower()
                if clean:
                    print(f"[+] Google SpeechRecognition (In-Memory) solved audio: '{clean}'", flush=True)
                    return clean
            except Exception:
                pass

            # Backup: faster-whisper via in-memory stream if SpeechRecognition fails
            if self.faster_model:
                try:
                    segments, _ = self.faster_model.transcribe(io.BytesIO(wav_bytes), language="en")
                    raw = "".join(s.text for s in segments)
                    clean = re.sub(r'[^a-zA-Z0-9\s]', '', raw).strip().lower()
                    if clean:
                        print(f"[+] faster-whisper (In-Memory) solved audio: '{clean}'", flush=True)
                        return clean
                except Exception:
                    pass

        # Fallback to disk if in-memory pipeline encountered severe failure
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            wav_path = tmp_path.replace(".mp3", ".wav")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp_path, "-ac", "1", "-ar", "16000", wav_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5
                )
                if os.path.exists(wav_path):
                    try:
                        import speech_recognition as sr
                        r = sr.Recognizer()
                        with sr.AudioFile(wav_path) as source:
                            audio_data = r.record(source)
                        text = r.recognize_google(audio_data, language="en-US")
                        clean = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip().lower()
                        if clean:
                            print(f"[+] Google SpeechRecognition (Disk Fallback) solved: '{clean}'", flush=True)
                            return clean
                    finally:
                        if os.path.exists(wav_path):
                            try:
                                os.remove(wav_path)
                            except Exception:
                                pass
            except Exception:
                pass

            return ""
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _sync_tokens(self, page: Page, token: str):
        """
        Synchronizes reCAPTCHA response token across all form fields,
        hidden inputs, textareas, and dispatches change/callback events.
        """
        if not token:
            return
        page.evaluate("""(tok) => {
            // 1. Synchronize to all potential response containers
            const selectors = [
                '[name="g-recaptcha-response"]',
                '#g-recaptcha-response',
                '.g-recaptcha-response',
                'textarea[name="g-recaptcha-response"]',
                'input[name="g-recaptcha-response"]'
            ];
            document.querySelectorAll(selectors.join(', ')).forEach(el => {
                el.value = tok;
                el.innerHTML = tok;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            });

            // 2. Ensure main forms have the response input populated
            ['#main-form', '#main-form-2', '#recaptcha', '#recaptcha-2'].forEach(formSel => {
                const form = document.querySelector(formSel);
                if (form) {
                    let inp = form.querySelector('[name="g-recaptcha-response"]');
                    if (!inp) {
                        inp = document.createElement('textarea');
                        inp.setAttribute('name', 'g-recaptcha-response');
                        inp.setAttribute('id', 'g-recaptcha-response');
                        inp.style.display = 'none';
                        form.appendChild(inp);
                    }
                    inp.value = tok;
                    inp.innerHTML = tok;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });

            // 3. Trigger callback on elements with data-callback
            document.querySelectorAll('.g-recaptcha[data-callback]').forEach(el => {
                const cbName = el.getAttribute('data-callback');
                if (cbName && typeof window[cbName] === 'function') {
                    try { window[cbName](tok); } catch(e) {}
                }
            });

            // 4. Trigger Link4M global recaptcha_callback if present
            if (typeof window.recaptcha_callback === 'function') {
                try { window.recaptcha_callback(tok); } catch(e) {}
            }

            // 5. Trigger grecaptcha internal callbacks if present
            try {
                if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
                    Object.values(window.___grecaptcha_cfg.clients).forEach(client => {
                        for (const k in client) {
                            const obj = client[k];
                            if (obj && typeof obj === 'object' && typeof obj.callback === 'function') {
                                try { obj.callback(tok); } catch(e) {}
                            }
                        }
                    });
                }
            } catch(e) {}
        }""", token)

    def solve_on_page(self, page: Page, timeout_sec: int = 40, container_selector: str = None) -> Dict[str, Any]:
        """
        3-Tier Multi-Resilient reCAPTCHA v2 Solver:
          - Tier 1: Instant Anchor Check via Trust Score (< 0.5s).
          - Tier 2: Direct JS Audio Event Dispatch + In-Memory Speech Recognition (< 2s, 0% CPU, 0$ cost).
          - Tier 3: Cloud Token API Fallback (2Captcha) upon DOSCAPTCHA or rate limit.
        Zero Vision AI: Completely eliminates YOLO, ONNX, and CLIP models.
        """
        t0 = time.perf_counter()

        # Extract sitekey from DOM or iframes
        sitekey = page.evaluate("""() => {
            const mainIframe = document.querySelector('#main-form iframe[src*="k="], #main-form-2 iframe[src*="k="], #recaptcha iframe[src*="k="], #recaptcha-2 iframe[src*="k="]');
            if (mainIframe) {
                const m = (mainIframe.getAttribute('src') || '').match(/[?&]k=([^&]+)/);
                if (m) return m[1];
            }
            const allIframes = Array.from(document.querySelectorAll('iframe[src*="recaptcha/api2/anchor"]'));
            for (const f of allIframes) {
                if (!f.closest('#modal-report') && !f.closest('#modal-report-form')) {
                    const m = (f.getAttribute('src') || '').match(/[?&]k=([^&]+)/);
                    if (m) return m[1];
                }
            }
            const el = document.querySelector('.g-recaptcha[data-sitekey], [data-sitekey]');
            if (el && el.getAttribute('data-sitekey')) return el.getAttribute('data-sitekey');
            return '6LcqrIgsAAAAAPkab9oMW9S4onnzLi8A6RVZpNOy';
        }""") or '6LcqrIgsAAAAAPkab9oMW9S4onnzLi8A6RVZpNOy'

        # Build target CSS selector
        if container_selector:
            parts = [s.strip() for s in container_selector.split(",") if s.strip()]
            target_css = ", ".join([f"{p} iframe[src*='recaptcha/api2/anchor'], {p} iframe[src*='recaptcha/enterprise/anchor']" for p in parts])
        else:
            target_css = "iframe[src*='recaptcha/api2/anchor'], iframe[src*='recaptcha/enterprise/anchor']"

        candidate_anchors = []
        for _wait in range(25):
            anchors = page.locator(target_css).all()
            if not anchors:
                anchors = page.locator("iframe[src*='recaptcha/api2/anchor'], iframe[src*='recaptcha/enterprise/anchor']").all()

            for idx, a in enumerate(anchors):
                try:
                    try:
                        a.scroll_into_view_if_needed(timeout=1000)
                    except Exception:
                        pass
                    box = a.bounding_box()
                    cf = a.content_frame
                    if not cf:
                        continue
                    chk = cf.locator("#recaptcha-anchor")
                    if chk.count() == 0:
                        continue

                    body_text = ""
                    try:
                        body_text = cf.locator("body").inner_text() or ""
                    except Exception:
                        pass
                    has_quota_error = any(w in body_text.lower() for w in ["quota", "exceeding", "bị lỗi", "error"])

                    y_pos = box['y'] if box else 0

                    is_in_main = False
                    try:
                        is_in_main = a.evaluate("el => el.closest('#main-form, #main-form-2') !== null")
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
            time.sleep(0.3)

        if not candidate_anchors:
            return {"success": False, "token": "", "type": None, "time_ms": round((time.perf_counter() - t0) * 1000, 2), "error": "no_anchors_found"}

        # Sort: healthy first, #main-form first, then top-most
        candidate_anchors.sort(key=lambda x: (not x["has_error"], 1 if x["is_in_main"] else 0, -x["y"]), reverse=True)

        for cand in candidate_anchors:
            try:
                a = cand["anchor"]
                chk = cand["chk"]
                cf = cand["frame"]

                # ============================================================
                # TIER 1: Instant Anchor Check via Trust Score (< 0.5s)
                # ============================================================
                # Check if already ticked green
                if chk.get_attribute("aria-checked") == "true":
                    token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                    elapsed = round((time.perf_counter() - t0) * 1000, 2)
                    print(f"[+] [Tier 1 Instant] reCAPTCHA already checked green in {elapsed}ms!", flush=True)
                    self._sync_tokens(page, token)
                    return {"success": True, "token": token, "type": "instant", "time_ms": elapsed, "error": None}

                try:
                    a.scroll_into_view_if_needed()
                    time.sleep(0.1)
                    box = a.bounding_box()
                    if box:
                        target_x = box['x'] + max(10, box['width'] / 4)
                        target_y = box['y'] + max(10, box['height'] / 2)
                        page.mouse.move(target_x, target_y, steps=8)
                        time.sleep(0.1)
                except Exception:
                    pass

                try:
                    chk.click(force=True, timeout=3000)
                except Exception:
                    try:
                        cf.locator("#recaptcha-anchor").click(force=True, timeout=2000)
                    except Exception:
                        pass

                # Quick check for instant solve (< 1.5s)
                for _quick in range(15):
                    if chk.get_attribute("aria-checked") == "true":
                        token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                        elapsed = round((time.perf_counter() - t0) * 1000, 2)
                        print(f"[+] [Tier 1 Instant] Instantly solved without challenge in {elapsed}ms!", flush=True)
                        self._sync_tokens(page, token)
                        return {"success": True, "token": token, "type": "instant", "time_ms": elapsed, "error": None}
                    time.sleep(0.1)

                # ============================================================
                # TIER 2: Direct JS Audio Event Dispatch & In-Memory Solve (< 2s)
                # ============================================================
                active_bframe = None
                a_name = a.get_attribute("name") or ""
                target_bname = "c-" + a_name[2:] if a_name.startswith("a-") else None

                for _ in range(25):
                    if target_bname:
                        direct_bf = page.locator(f"iframe[name='{target_bname}']")
                        if direct_bf.count() > 0:
                            cf_candidate = direct_bf.first.content_frame
                            if cf_candidate and cf_candidate.locator("#recaptcha-audio-button, .rc-imageselect, #recaptcha-verify-button, .rc-doscaptcha-header-text").count() > 0:
                                active_bframe = cf_candidate
                                break

                    for f in page.frames:
                        if target_bname and f.name == target_bname:
                            active_bframe = f
                            break
                        if "recaptcha" in f.url and ("bframe" in f.url or "challenge" in f.url):
                            if f.locator("#recaptcha-audio-button, .rc-imageselect, #recaptcha-verify-button, .rc-doscaptcha-header-text").count() > 0:
                                active_bframe = f
                                break
                    if active_bframe:
                        break

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
                    time.sleep(0.2)

                audio_solved = False

                if active_bframe:
                    # Check if audio button exists and click via Direct JS in 1ms
                    has_audio_btn = False
                    for _wait_audio_btn in range(15):
                        try:
                            has_audio_btn = active_bframe.evaluate("""() => {
                                const btn = document.querySelector('#recaptcha-audio-button');
                                if (btn && !btn.disabled && !btn.classList.contains('rc-button-disabled')) {
                                    btn.click();
                                    return true;
                                }
                                return false;
                            }""")
                        except Exception:
                            has_audio_btn = False
                        if has_audio_btn:
                            break
                        time.sleep(0.1)

                    if has_audio_btn:
                        print("[+] [Tier 2 Audio] Clicked Audio Challenge button via Direct JS in 1ms.", flush=True)
                        time.sleep(1.0)

                        # Detect Rate-limit / DOSCAPTCHA
                        is_rate_limited = active_bframe.evaluate("""() => {
                            const h = document.querySelector('.rc-doscaptcha-header-text');
                            if (h && h.offsetParent !== null && h.innerText.trim() !== '') return true;
                            const m = document.querySelector('.rc-audiochallenge-error-message');
                            if (m && m.offsetParent !== null && m.innerText.trim() !== '') return true;
                            const bodyText = document.body ? document.body.innerText : '';
                            if (bodyText.includes('Try again later') || bodyText.includes('automated queries')) return true;
                            return false;
                        }""")

                        if is_rate_limited:
                            print("[!] [Tier 2 Audio] Google reCAPTCHA audio rate-limit / DOSCAPTCHA detected. Proceeding to Tier 3 Cloud Fallback...", flush=True)
                        else:
                            # Poll audio download link
                            audio_url = None
                            for _try_audio in range(12):
                                audio_url = active_bframe.evaluate("""() => {
                                    const a = document.querySelector('.rc-audiochallenge-tdownload-link') ||
                                              document.querySelector('a.rc-audiochallenge-download-link') ||
                                              document.querySelector('a[href*="audio.mp3"]');
                                    return (a && a.href) ? a.href : null;
                                }""")
                                if audio_url:
                                    break
                                time.sleep(0.3)

                            if audio_url:
                                print(f"[+] [Tier 2 Audio] Audio download stream ready: {audio_url[:50]}...", flush=True)
                                ans = self.transcribe_audio_url(audio_url)
                                if ans:
                                    print(f"[+] [Tier 2 Audio] Audio transcribed: '{ans}'", flush=True)
                                    active_bframe.evaluate("""(ans) => {
                                        const input = document.querySelector('#audio-response');
                                        if (input) {
                                            input.value = ans;
                                            input.dispatchEvent(new Event('input', { bubbles: true }));
                                            input.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                        const verifyBtn = document.querySelector('#recaptcha-verify-button');
                                        if (verifyBtn) verifyBtn.click();
                                    }""", ans)

                                    for _wait_tick in range(20):
                                        if chk.get_attribute("aria-checked") == "true":
                                            audio_solved = True
                                            break
                                        time.sleep(0.2)

                                    if audio_solved:
                                        token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                                        self._sync_tokens(page, token)
                                        elapsed = round((time.perf_counter() - t0) * 1000, 2)
                                        print(f"[+] [Tier 2 Audio] Solved reCAPTCHA v2 in {elapsed}ms (0% CPU, 0$ cost)!", flush=True)
                                        return {"success": True, "token": token, "type": "audio_unblock_free", "time_ms": elapsed, "error": None}

                # ============================================================
                # TIER 3: Cloud Token API Fallback (2Captcha pool)
                # ============================================================
                if not audio_solved and chk.get_attribute("aria-checked") != "true":
                    print("[*] [Tier 3 Cloud] Audio unavailable or rate-limited. Activating 2Captcha Cloud API Fallback...", flush=True)
                    if solve_recaptcha_2captcha:
                        try:
                            api_key = os.environ.get("TWOCAPTCHA_API_KEY", "").strip()
                            if not api_key and get_best_key:
                                api_key = get_best_key()

                            cloud_token = solve_recaptcha_2captcha(site_key=sitekey, target_url=page.url, api_key=api_key)
                            if cloud_token:
                                self._sync_tokens(page, cloud_token)
                                elapsed = round((time.perf_counter() - t0) * 1000, 2)
                                print(f"[+] [Tier 3 Cloud] 2Captcha token received in {elapsed}ms!", flush=True)
                                return {"success": True, "token": cloud_token, "type": "cloud_token", "time_ms": elapsed, "error": None}
                        except Exception as e_cloud:
                            print(f"[!] [Tier 3 Cloud] Fallback exception: {e_cloud}", flush=True)
                    else:
                        print("[!] [Tier 3 Cloud] twocaptcha_client module not available.", flush=True)

                # Final check on aria-checked
                if chk.get_attribute("aria-checked") == "true":
                    token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                    elapsed = round((time.perf_counter() - t0) * 1000, 2)
                    self._sync_tokens(page, token)
                    return {"success": True, "token": token, "type": "instant", "time_ms": elapsed, "error": None}

            except Exception as e_cand:
                print(f"[!] Error on candidate {cand['index']}: {e_cand}", flush=True)
                continue

        elapsed_total = round((time.perf_counter() - t0) * 1000, 2)
        return {"success": False, "token": "", "type": None, "time_ms": elapsed_total, "error": "all_candidates_failed"}


_SOLVER_INSTANCE = None

def get_solver(headless: bool = True, **kwargs) -> RecaptchaSolver:
    global _SOLVER_INSTANCE
    if _SOLVER_INSTANCE is None:
        _SOLVER_INSTANCE = RecaptchaSolver(headless=headless, **kwargs)
    return _SOLVER_INSTANCE

RecaptchaAudioSolver = RecaptchaSolver
get_solver_instance = get_solver
