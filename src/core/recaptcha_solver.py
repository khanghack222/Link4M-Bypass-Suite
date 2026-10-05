import sys
import os

_py311_site = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "Lib", "site-packages")
if os.path.exists(_py311_site) and _py311_site not in sys.path:
    sys.path.insert(0, _py311_site)

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
        self._yolo_detector = None

    @property
    def yolo_detector(self):
        if self._yolo_detector is None:
            try:
                from vision_ai_recaptcha_solver.detector import YOLODetector
                yolo_model_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "yolo12x.pt")
                if not os.path.exists(yolo_model_file):
                    yolo_model_file = "yolo12x.pt"
                self._yolo_detector = YOLODetector(detection_model_path=yolo_model_file)
                print("[+] Local YOLOv12x & Classification 57k detector loaded successfully.", flush=True)
            except Exception as e:
                print(f"[!] Could not load local YOLO detector: {e}", flush=True)
                self._yolo_detector = False
        return self._yolo_detector if self._yolo_detector is not False else None

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
    def clip_model(self):
        if not hasattr(self, "_clip_model") or self._clip_model is None:
            try:
                import torch
                from transformers import CLIPProcessor, CLIPModel
                print("[*] Initializing OpenAI CLIP ViT-B/32 Zero-Shot Classifier...", flush=True)
                device = "cuda" if torch.cuda.is_available() else "cpu"
                model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
                processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                self._clip_model = (model, processor, device)
                print("[+] OpenAI CLIP ViT-B/32 loaded successfully.", flush=True)
            except Exception as e:
                print(f"[!] Could not load CLIP model: {e}", flush=True)
                self._clip_model = False
        return self._clip_model if self._clip_model is not False else None

    def ask_clip_tiles(self, img_bytes: bytes, instruction: str, total_tiles: int = 9) -> List[int]:
        clip_data = self.clip_model
        if not clip_data:
            return []
        try:
            import io, re, torch
            from PIL import Image

            model, processor, device = clip_data
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            w, h = img.size
            grid_n = 4 if total_tiles == 16 else 3
            tw, th = w // grid_n, h // grid_n

            inst_lower = instruction.lower()
            target_noun = ""
            MAPPINGS = [
                ("crosswalk", "pedestrian crosswalk white painted stripes on road asphalt"),
                ("crosswalks", "pedestrian crosswalk white painted stripes on road asphalt"),
                ("traffic light", "traffic signal light with red yellow green lamps"),
                ("traffic lights", "traffic signal light with red yellow green lamps"),
                ("fire hydrant", "red or yellow street fire hydrant"),
                ("fire hydrants", "red or yellow street fire hydrant"),
                ("bus", "public transit city bus or motorcoach vehicle"),
                ("buses", "public transit city bus or motorcoach vehicle"),
                ("bicycle", "bicycle or cyclist on bike"),
                ("bicycles", "bicycle or cyclist on bike"),
                ("motorcycle", "motorcycle, motorbike or scooter"),
                ("motorcycles", "motorcycle, motorbike or scooter"),
                ("car", "passenger automobile car or sedan or suv vehicle"),
                ("cars", "passenger automobile car or sedan or suv vehicle"),
                ("truck", "cargo freight truck or pickup truck"),
                ("trucks", "cargo freight truck or pickup truck"),
                ("stairs", "outdoor concrete stairs staircase steps"),
                ("bridge", "bridge or overpass over water or highway"),
                ("chimney", "brick or stone building roof chimney"),
                ("tractor", "farm tractor vehicle in field"),
                ("palm tree", "tall tropical palm tree with fronds"),
                ("boat", "boat or ship vessel on water"),
                ("parking meter", "street parking meter pole"),
                ("parking meters", "street parking meter pole")
            ]
            for kw, desc in MAPPINGS:
                if kw in inst_lower:
                    target_noun = desc
                    break

            if not target_noun:
                m = re.search(r'(?:with|containing(?:\s+a)?)\s+([a-zA-Z\s]+?)(?:\s+(?:click|once|if)|$|\n)', inst_lower)
                if m:
                    extracted = m.group(1).strip()
                    if extracted and len(extracted) > 2:
                        target_noun = extracted
            if not target_noun:
                target_noun = "object"

            tiles = []
            for r in range(grid_n):
                for c in range(grid_n):
                    tile = img.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))
                    tiles.append(tile)

            labels = [
                f"a photo containing a {target_noun}",
                f"a photo of an empty street, road, pavement, trees or sky without any {target_noun}"
            ]

            inputs = processor(text=labels, images=tiles, return_tensors="pt", padding=True).to(device)
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits_per_image
                probs = logits.softmax(dim=1).cpu().numpy()

            scored_tiles = []
            thresh = 0.65 if total_tiles == 16 else 0.68
            for idx, p in enumerate(probs):
                tile_num = idx + 1
                conf = float(p[0])
                if conf >= thresh:
                    scored_tiles.append((tile_num, conf))

            scored_tiles.sort(key=lambda x: x[1], reverse=True)
            max_allowed = 6 if total_tiles == 16 else 4
            matched = [t[0] for t in scored_tiles[:max_allowed]]

            if matched:
                print(f"[+] [OpenAI CLIP Zero-Shot] Matched tiles for '{target_noun[:30]}': {matched}", flush=True)
            return matched
        except Exception as e:
            print(f"[!] CLIP inference error: {e}", flush=True)
            return []

    def transcribe_audio_url(self, audio_url: str) -> str:
        # Priority 0: API Client if available
        try:
            from captcha_api_client import solve_audio_recaptcha
            res_text = solve_audio_recaptcha(audio_url=audio_url)
            if res_text:
                return res_text.strip().lower()
        except Exception:
            pass

        # Fetch MP3 bytes in-memory
        try:
            req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                audio_bytes = resp.read()
        except Exception as e:
            print(f"[!] Failed to fetch audio stream: {e}", flush=True)
            return ""

        # Priority 1: In-Memory Conversion (Zero Disk I/O)
        wav_bytes = None
        try:
            from pydub import AudioSegment
            import io
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            seg = seg.set_frame_rate(16000).set_channels(1)
            wav_buf = io.BytesIO()
            seg.export(wav_buf, format="wav")
            wav_bytes = wav_buf.getvalue()
        except Exception:
            wav_bytes = None

        if wav_bytes:
            # 1a. Google SpeechRecognition via In-Memory AudioData (Fastest, 0 disk, ~300ms)
            try:
                import speech_recognition as sr
                import io
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

            # 1b. faster-whisper via in-memory stream
            if self.faster_model:
                try:
                    import io
                    segments, _ = self.faster_model.transcribe(io.BytesIO(wav_bytes), language="en")
                    raw = "".join(s.text for s in segments)
                    clean = re.sub(r'[^a-zA-Z0-9\s]', '', raw).strip().lower()
                    if clean:
                        print(f"[+] faster-whisper (In-Memory) solved audio: '{clean}'", flush=True)
                        return clean
                except Exception:
                    pass

        # Priority 2: Disk fallback if in-memory pipeline fails
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

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
                            print(f"[+] Google SpeechRecognition (Disk Fallback) solved: '{clean}'", flush=True)
                            return clean
                    finally:
                        try: os.remove(wav_path)
                        except Exception: pass
            except Exception:
                pass

            if self.faster_model:
                try:
                    segments, _ = self.faster_model.transcribe(tmp_path, language="en")
                    raw = "".join(s.text for s in segments)
                    clean = re.sub(r'[^a-zA-Z0-9\s]', '', raw).strip().lower()
                    if clean:
                        print(f"[+] faster-whisper (Disk Fallback) solved: '{clean}'", flush=True)
                        return clean
                except Exception:
                    pass

            if self.model:
                res = self.model.transcribe(tmp_path, language="en", fp16=False)
                return re.sub(r'[^a-zA-Z0-9\s]', '', res.get("text", "")).strip().lower()

            return ""
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    def ask_gemini_vision_tiles(self, img_bytes: bytes, instruction: str, total_tiles: int = 9) -> List[int]:
        # Priority 0: WebAI-to-API Gemini Vision (Zero-cost, Pro Tier WebAPI)
        try:
            try:
                from webai_client import is_webai_available, solve_recaptcha_v2_webai
            except ImportError:
                from src.core.webai_client import is_webai_available, solve_recaptcha_v2_webai

            if is_webai_available():
                tiles = solve_recaptcha_v2_webai(img_bytes, instruction=instruction, total_tiles=total_tiles)
                if tiles:
                    print(f"[+] 🧠 [WebAI-to-API Vision] Identified reCAPTCHA tiles: {tiles}", flush=True)
                    return tiles
        except Exception:
            pass

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

        models = ["gemini-flash-lite-latest", "gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
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

    def ask_local_onnx_tiles(self, img_bytes: bytes, instruction: str, total_tiles: int = 9) -> List[int]:
        """Classifies tiles locally via YOLOv12x & ONNX reCAPTCHA 57k models in sub-100ms with zero token cost."""
        try:
            import cv2
            import numpy as np

            arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            if arr is None:
                return []
            h, w = arr.shape[:2]

            # Priority 1: YOLODetector (YOLOv12x for 4x4 detection & ONNX 57k for 3x3 classification)
            yd = self.yolo_detector
            if yd:
                if total_tiles == 16:
                    coco_cls = yd.get_coco_target_class(instruction)
                    if coco_cls is not None:
                        cells = yd.detect_for_grid(arr, target_class=coco_cls, grid_size=w)
                        if cells:
                            print(f"[+] [YOLOv12x Detection] 4x4 cells detected: {cells}", flush=True)
                            return cells
                    # Fallback to classification for 4x4 if COCO class didn't hit
                    tgt_cls = yd.get_target_class(instruction)
                    if tgt_cls is not None:
                        cells_conf = yd.classify_tiles_with_confidence(arr, grid_size=4, target_class=tgt_cls)
                        matched = [c for c, conf in cells_conf if conf >= 0.50]
                        if matched:
                            print(f"[+] [Classification 57k] 4x4 tiles detected: {matched}", flush=True)
                            return matched[:6]
                else:
                    tgt_cls = yd.get_target_class(instruction)
                    if tgt_cls is not None:
                        cells_conf = yd.classify_tiles_with_confidence(arr, grid_size=3, target_class=tgt_cls)
                        matched = [c for c, conf in cells_conf if conf >= 0.40]
                        if not matched and cells_conf:
                            top = sorted(cells_conf, key=lambda x: x[1], reverse=True)
                            if top and top[0][1] >= 0.25:
                                matched = [top[0][0]]
                        if matched:
                            print(f"[+] [Classification 57k] 3x3 tiles detected: {matched}", flush=True)
                            return matched

            # Priority 2: Direct ONNX Runtime Session Fallback
            import onnxruntime as ort
            from vision_ai_recaptcha_solver.detector.yolo_detector import TARGET_MAPPINGS

            model_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Programs", "Python", "Python311", "Lib", "site-packages",
                "vision_ai_recaptcha_solver", "models", "recaptcha_classification_57k.onnx"
            )
            if not os.path.exists(model_path):
                return []

            sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
            grid_n = 4 if total_tiles == 16 else 3
            th, tw = h // grid_n, w // grid_n

            keyword = ''
            norm_inst = instruction.lower()
            for k in sorted(TARGET_MAPPINGS.keys(), key=len, reverse=True):
                if k in norm_inst:
                    keyword = k
                    break
            if not keyword:
                return []
            target_class = TARGET_MAPPINGS[keyword]

            blobs = []
            for row in range(grid_n):
                for col in range(grid_n):
                    tile = arr[row*th:(row+1)*th, col*tw:(col+1)*tw]
                    resized = cv2.resize(tile, (128, 128))
                    b = np.transpose(resized, (2, 0, 1)).astype(np.float32) / 255.0
                    blobs.append(b)

            blobs = np.array(blobs)
            outs = sess.run(None, {'images': blobs})[0]

            matched_tiles = []
            for idx, out in enumerate(outs):
                tile_num = idx + 1
                exp_out = np.exp(out - np.max(out))
                probs = exp_out / np.sum(exp_out)
                target_prob = probs[target_class]
                pred_class = np.argmax(probs)
                min_threshold = 0.55 if total_tiles == 16 else 0.40
                if pred_class == target_class or target_prob >= min_threshold:
                    matched_tiles.append((tile_num, float(target_prob)))

            matched_tiles.sort(key=lambda x: x[1], reverse=True)
            max_allowed = 6 if total_tiles == 16 else 4
            res = [t[0] for t in matched_tiles[:max_allowed]]
            if res:
                print(f"[+] [Local ONNX Direct] Target '{keyword}' (class {target_class}) detected in tiles: {res}", flush=True)
            return res
        except Exception as e:
            print(f"[!] Local ONNX tile error: {e}", flush=True)
            return []

    def solve_image_challenge(self, page: Page, active_bframe, chk, max_rounds: int = 20) -> bool:
        """Solves reCAPTCHA v2 image challenge using Local ONNX Classification model & Gemini Vision fallback."""
        print("[*] Starting Visual Image Challenge Solver for reCAPTCHA...", flush=True)
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

            def get_grid_screenshot():
                for sel in [
                    "table.rc-imageselect-table-33", "table.rc-imageselect-table-44",
                    ".rc-imageselect-target table", ".rc-imageselect-target",
                    ".rc-imageselect-challenge", "body"
                ]:
                    try:
                        loc = active_bframe.locator(sel)
                        if loc.count() > 0:
                            return loc.first.screenshot(timeout=3000)
                    except Exception:
                        pass
                return None

            img_bytes = get_grid_screenshot()
            if not img_bytes:
                break

            tiles = active_bframe.locator("td.rc-imageselect-tile")
            tile_count = tiles.count()
            total_tiles = 16 if tile_count == 16 else 9

            tiles_to_click = []

            # Priority 1: Fast local ONNX 57k & YOLOv12x detector (sub-50ms)
            tiles_to_click = self.ask_local_onnx_tiles(img_bytes, instruction, total_tiles=total_tiles)

            # Priority 1.5: WebAI-to-API Gemini Vision (High-Precision Multimodal AI)
            if not tiles_to_click:
                tiles_to_click = self.ask_gemini_vision_tiles(img_bytes, instruction, total_tiles=total_tiles)

            # Priority 2: Reload 4x4 grid if ambiguous to get simple 3x3 challenge
            if not tiles_to_click and total_tiles == 16:
                reload_btn = active_bframe.locator("#recaptcha-reload-button")
                if reload_btn.is_visible():
                    print("[*] 4x4 grid ambiguous. Reloading for clean 3x3 challenge...", flush=True)
                    try:
                        reload_btn.evaluate("el => el.click()")
                    except Exception:
                        pass
                    time.sleep(1.8)
                    continue

            # Priority 3: OpenAI CLIP Zero-Shot fallback
            if not tiles_to_click:
                tiles_to_click = self.ask_clip_tiles(img_bytes, instruction, total_tiles=total_tiles)

            if not tiles_to_click:
                is_skip = "click skip" in instruction.lower() or "if there are none" in instruction.lower()
                verify_btn = active_bframe.locator("#recaptcha-verify-button")
                if is_skip and verify_btn.is_visible():
                    verify_btn.evaluate("el => el.click()")
                    time.sleep(2.0)
                else:
                    reload_btn = active_bframe.locator("#recaptcha-reload-button")
                    if reload_btn.is_visible():
                        reload_btn.evaluate("el => el.click()")
                        time.sleep(2.0)
                    elif verify_btn.is_visible():
                        verify_btn.evaluate("el => el.click()")
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
                            try:
                                tile.evaluate("el => el.click()")
                            except Exception:
                                pass
                            time.sleep(0.2)
                    time.sleep(2.5)
                    img_bytes = get_grid_screenshot()
                    if not img_bytes:
                        break
                    tiles = active_bframe.locator("td.rc-imageselect-tile")
                    tiles_to_click = self.ask_local_onnx_tiles(img_bytes, instruction, total_tiles=total_tiles)
                    if not tiles_to_click:
                        print("[+] Dynamic loop: No more targets detected. Ready to VERIFY.", flush=True)
                        break
            else:
                for idx in tiles_to_click:
                    if 1 <= idx <= total_tiles:
                        tile = tiles.nth(idx - 1)
                        try:
                            tile.evaluate("el => el.click()")
                        except Exception:
                            pass
                        time.sleep(0.2)

            time.sleep(0.6)
            verify_btn = active_bframe.locator("#recaptcha-verify-button")
            if verify_btn.is_visible():
                btn_txt = verify_btn.inner_text().strip()
                print(f"[+] Clicking challenge button: '{btn_txt}'", flush=True)
                try:
                    verify_btn.evaluate("el => el.click()")
                except Exception:
                    try:
                        verify_btn.click(force=True, timeout=1500)
                    except Exception:
                        pass

            # Chờ Google backend verify kết quả và tick xanh checkbox (tối đa 6 giây)
            for _wait_chk in range(12):
                if chk.get_attribute("aria-checked") == "true":
                    print("[+] reCAPTCHA verified and checked green!", flush=True)
                    return True
                time.sleep(0.5)

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

        # Priority 0: PassXAPI Cloud Solver with Residential Proxy (Instant Sub-6s token)
        try:
            try:
                from passx_client import solve_recaptcha_passx
            except ImportError:
                from src.core.passx_client import solve_recaptcha_passx

            sitekey = page.evaluate("""() => {
                let el = document.querySelector('.g-recaptcha, [data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : '6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ';
            }""") or '6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ'

            passx_token = solve_recaptcha_passx(site_key=sitekey, target_url=page.url, version="v2", max_wait=16.0)
            if passx_token:
                self._sync_tokens(page, passx_token)
                elapsed = round((time.perf_counter() - t0) * 1000, 2)
                print(f"[+] [PassXAPI] Injected valid reCAPTCHA token into page inputs in {elapsed}ms (len={len(passx_token)})", flush=True)
        except Exception as e_passx:
            print(f"[!] PassXAPI note: {e_passx}", flush=True)

        # Priority 0.5: 2captcha API Fallback
        try:
            from twocaptcha_client import solve_recaptcha_2captcha
            two_token = solve_recaptcha_2captcha(site_key=sitekey, target_url=page.url, max_wait=30.0)
            if two_token:
                self._sync_tokens(page, two_token)
                elapsed = round((time.perf_counter() - t0) * 1000, 2)
                print(f"[+] [2Captcha] Injected token into page inputs in {elapsed}ms (len={len(two_token)})", flush=True)
                return {"success": True, "token": two_token, "type": "2captcha_cloud", "time_ms": elapsed}
        except Exception as e_two:
            print(f"[!] 2captcha fallback note: {e_two}", flush=True)

        # Build strict target CSS without selector bleeding
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

                    # Detect if anchor is inside form
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
                    time.sleep(0.2)
                    box = a.bounding_box()
                    if box:
                        target_x = box['x'] + max(10, box['width'] / 4)
                        target_y = box['y'] + max(10, box['height'] / 2)
                        page.mouse.move(target_x, target_y, steps=15)
                        time.sleep(0.25)
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

                    # Secondary: search in page.frames
                    for f in page.frames:
                        if target_bname and f.name == target_bname:
                            active_bframe = f
                            break
                        if "recaptcha" in f.url and ("bframe" in f.url or "challenge" in f.url):
                            if f.locator("#recaptcha-audio-button, .rc-imageselect, #recaptcha-verify-button").count() > 0:
                                active_bframe = f
                                break
                    if active_bframe:
                        break

                    # Tertiary: check all bframe locators
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

                # --- STEP 1: Attempt Visual Challenge if already present (Fastest & avoids DOSCAPTCHA) ---
                solved = False
                has_visual = active_bframe.locator(".rc-imageselect-instructions, .rc-imageselect-desc, .rc-imageselect-desc-no-canonical, .rc-imageselect").count() > 0
                if has_visual:
                    print("[+] Visual challenge already presented. Solving via AI (max 4 rounds)...", flush=True)
                    solved = self.solve_image_challenge(page, active_bframe, chk, max_rounds=4)

                # --- STEP 2: Fallback to Audio Challenge ONLY if no visual challenge and not solved ---
                if not solved and chk.get_attribute("aria-checked") != "true":
                    audio_btn = active_bframe.locator("#recaptcha-audio-button")
                    if audio_btn.count() > 0:
                        btn_class = audio_btn.get_attribute("class") or ""
                        if "rc-button-disabled" not in btn_class and not audio_btn.get_attribute("disabled"):
                            try:
                                audio_btn.scroll_into_view_if_needed()
                                audio_btn.click(force=True, timeout=2000)
                                print("[+] Audio challenge requested...", flush=True)
                                time.sleep(1.2)

                                is_doscaptcha = active_bframe.locator(".rc-doscaptcha-header-text, .rc-audiochallenge-error-message").count() > 0
                                if not is_doscaptcha:
                                    download_link = active_bframe.locator(".rc-audiochallenge-tdownload-link, a:has-text('Download')")
                                    try:
                                        download_link.wait_for(state="visible", timeout=4000)
                                        audio_url = download_link.get_attribute("href")
                                    except Exception:
                                        audio_url = None

                                    if audio_url:
                                        ans = self.transcribe_audio_url(audio_url)
                                        if ans:
                                            print(f"[+] Audio transcribed: '{ans}'", flush=True)
                                            input_field = active_bframe.locator("#audio-response")
                                            input_field.fill(ans)
                                            active_bframe.locator("#recaptcha-verify-button").click()
                                            time.sleep(2.0)
                                            if chk.get_attribute("aria-checked") == "true":
                                                solved = True
                            except Exception as ex:
                                print(f"[!] Audio attempt error: {ex}", flush=True)

                # --- STEP 3: Fallback back to Visual Challenge if still not solved ---
                if not solved and chk.get_attribute("aria-checked") != "true":
                    img_btn = active_bframe.locator("#recaptcha-image-button")
                    if img_btn.count() > 0 and img_btn.is_visible():
                        try:
                            img_btn.click(force=True, timeout=1500)
                            time.sleep(1.0)
                        except Exception:
                            pass
                    solved = self.solve_image_challenge(page, active_bframe, chk, max_rounds=15)

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

