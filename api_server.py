#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
⚡ LINK4M / BYPASS SUITE - CENTRALIZED CAPTCHA & OCR MICROSERVICE SERVER ⚡
=============================================================================
Features (v2.5.0 Omni-Precision Architecture):
  1. GET  /health & /api/v1/status  : Live RAM, model status & safe health limit
  2. POST /api/v1/cv/analyze-tiles  : 9-Tile geometric CV solver (star, circle, triangle, etc.)
  3. POST /api/v1/audio/transcribe  : DSP noise filter + Whisper / Google Speech -> digit string
  4. POST /api/v1/ocr/resolve-domain: RapidOCR text extraction with domain de-obfuscation
  5. POST /api/v1/ocr/upload        : Direct image file upload for domain OCR
  6. POST /api/v1/turnstile/solve   : Cloudflare Turnstile automated solver pool
  7. POST /api/v1/link/decode       : Fast parameter unpacking & 301/302 redirect resolver
=============================================================================
"""

import sys
import os
import time
import re
import io
import ssl
import json
import base64
import gc
import asyncio
import urllib.request
import urllib.parse
from typing import Optional, List, Dict, Any, Union
from concurrent.futures import ThreadPoolExecutor

# Ensure paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")
CORE_DIR = os.path.join(SRC_DIR, "core")
for p in [CURRENT_DIR, SRC_DIR, CORE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import numpy as np
from PIL import Image
import cv2
import psutil

# Long-term stability & memory control
os.environ["MALLOC_ARENA_MAX"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"

_PROCESS = psutil.Process(os.getpid())
_REQUEST_COUNTER = 0
_OCR_ENGINE = None
_WHISPER_MODEL = None
_THREAD_POOL = ThreadPoolExecutor(max_workers=16)

# Resilient HTTP Client
_HTTP = requests.Session()
_retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
_HTTP.mount("https://", HTTPAdapter(max_retries=_retries, pool_connections=16, pool_maxsize=16))
_HTTP.mount("http://", HTTPAdapter(max_retries=_retries, pool_connections=16, pool_maxsize=16))

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# -----------------------------------------------------------------------------
# Lazy Model Singletons
# -----------------------------------------------------------------------------
def get_rapidocr():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        print("[*] Loading RapidOCR ONNX Runtime engine...", flush=True)
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
        print("[+] RapidOCR engine ready.", flush=True)
    return _OCR_ENGINE

def get_whisper(model_name: str = "tiny.en"):
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        print(f"[*] Loading Whisper '{model_name}' model...", flush=True)
        try:
            import whisper
            _WHISPER_MODEL = whisper.load_model(model_name)
            print(f"[+] Whisper '{model_name}' loaded.", flush=True)
        except Exception as e:
            print(f"[!] Whisper model load error: {e}", flush=True)
            _WHISPER_MODEL = None
    return _WHISPER_MODEL

def get_ram_mb() -> float:
    try:
        return round(_PROCESS.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return 0.0

def safe_downscale_image(image_bytes: bytes, max_dim: int = 1280) -> bytes:
    try:
        im = Image.open(io.BytesIO(image_bytes))
        w, h = im.size
        if max(w, h) > max_dim:
            im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        return image_bytes
    except Exception:
        return image_bytes

def check_and_gc():
    global _REQUEST_COUNTER
    _REQUEST_COUNTER += 1
    if _REQUEST_COUNTER % 25 == 0:
        gc.collect()

# -----------------------------------------------------------------------------
# FastAPI App Setup
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Link4M Bypass Suite Microservice API",
    description="Centralized Microservice for Computer Vision (QCaptcha 9-tile), Audio DSP Transcription, RapidOCR, Link Decoder & Cloudflare Turnstile.",
    version="2.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------
class OcrRequest(BaseModel):
    image_url: Optional[str] = Field(None, description="URL of screenshot or image")
    image_base64: Optional[str] = Field(None, description="Base64 encoded image string")
    filter_traffic_widgets: bool = Field(False, description="Filter traffic widgets")

class OcrResponse(BaseModel):
    domains: List[str]
    raw_text: List[str]
    elapsed_ms: float
    ram_used_mb: float

class TileItem(BaseModel):
    idx: int
    url: str

class TileAnalyzeRequest(BaseModel):
    tiles: Optional[List[TileItem]] = Field(None, description="List of TileItems with idx and url")
    tile_urls: Optional[List[str]] = Field(None, description="List of 9 tile image URLs")
    target_shape: Optional[str] = Field(None, description="Target shape: star, circle, triangle, hexagon, rectangle, cross")
    min_confidence: float = Field(0.55, description="Minimum confidence threshold (0.0 to 1.0)")

class AudioTranscribeRequest(BaseModel):
    audio_url: Optional[str] = Field(None, description="URL of .mp3 / .wav audio")
    audio_base64: Optional[str] = Field(None, description="Base64 encoded audio")
    language: str = Field("en-US", description="Language code")
    apply_dsp_filter: bool = Field(True, description="Apply bandpass filter and volume normalization")
    model: str = Field("tiny.en", description="Whisper model name")

class DecodeLinkRequest(BaseModel):
    url: str = Field(..., description="Encoded URL (/go/file/ or base64) or redirect link")
    follow_redirects: bool = Field(True, description="Follow 301/302 redirects")

class TurnstileSolveRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL")
    sitekey: str = Field(..., description="Cloudflare Turnstile sitekey")
    headless: bool = Field(True, description="Headless browser mode")
    timeout_seconds: Optional[int] = Field(30, alias="timeout_sec", description="Timeout in seconds")
    worker_url: Optional[str] = Field(None, description="Optional worker endpoint")

# -----------------------------------------------------------------------------
# Domain & OCR Helper Logic
# -----------------------------------------------------------------------------
IGNORE_DOMAINS = {
    'google.com', 'google.com.vn', 'shopee.vn', 'youtube.com', 'facebook.com',
    'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'wikipedia.org',
    'scholar.google.com', 't.me', 'telegram.org', 'linkhuongdan.online', 'octolink.vip',
    'play.google.com', 'mudeo.app', 'apps.apple.com', 'placehold.co'
}
JUNK_TLD = ('.app', '.play', '.png', '.jpg', '.jpeg', '.webp')

def deobfuscate_text(text: str) -> str:
    """Normalize obfuscated domain text (e.g. 'shopeefood [dot] vn', 'shopeefood(.)vn')."""
    t = text
    t = re.sub(r'\[dot\]|\(dot\)|\{dot\}|\s+dot\s+|\[\.\]|\(\.\)', '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*\.\s*', '.', t)
    return t

def extract_domains_from_text(lines: list) -> tuple:
    candidates = []
    raw_texts = []
    if not lines:
        return candidates, raw_texts

    for item in lines:
        text = item[1].strip()
        raw_texts.append(text)
        normalized = deobfuscate_text(text)

        for part in normalized.split():
            clean_part = part.strip('()[]{}<>,;:\'\"')
            match = re.search(r'(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', clean_part)
            if match:
                domain = match.group(1).lower()
                if domain in IGNORE_DOMAINS or any(domain.endswith(ext) for ext in JUNK_TLD):
                    continue
                if domain not in candidates:
                    candidates.append(domain)
    return candidates, raw_texts

# -----------------------------------------------------------------------------
# QCaptcha 9-Tile CV Analysis Logic
# -----------------------------------------------------------------------------
def analyze_single_tile(idx: int, url: str) -> dict:
    """High-precision geometric & contour analysis for one captcha tile."""
    if url.startswith('/'):
        url = 'https://frame.103-141-140-153.sslip.io' + url

    try:
        if url.startswith("data:image"):
            b64_data = url.split(",")[-1]
            content = base64.b64decode(b64_data)
        else:
            resp = _HTTP.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            if resp.status_code != 200:
                return {"idx": idx, "shape": "http_error", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": 0.0}
            content = resp.content

        im = Image.open(io.BytesIO(content)).convert('RGB')
        arr = np.array(im)
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        mask = (hsv[:, :, 1] > 30) | (hsv[:, :, 2] < 150)
        mask_u8 = mask.astype(np.uint8) * 255

        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return {"idx": idx, "shape": "blank", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": 0.0}

        c = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(c))
        peri = float(cv2.arcLength(c, True))
        if area < 10 or peri == 0:
            return {"idx": idx, "shape": "blank", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": area}

        approx = cv2.approxPolyDP(c, 0.035 * peri, True)
        num_v = len(approx)
        circ = (4 * np.pi * area) / (peri * peri) if peri > 0 else 0.0

        hull = cv2.convexHull(c)
        hull_area = float(cv2.contourArea(hull))
        solidity = (area / hull_area) if hull_area > 0 else 0.0

        x, y, w, h = cv2.boundingRect(c)
        aspect_ratio = round(float(w) / h, 2) if h > 0 else 0.0
        extent = round(area / (w * h), 2) if (w * h) > 0 else 0.0

        # Calculate convexity defects
        defects_count = 0
        try:
            hull_idx = cv2.convexHull(c, returnPoints=False)
            if len(hull_idx) > 3 and len(c) > 3:
                defects = cv2.convexityDefects(c, hull_idx)
                if defects is not None:
                    for i in range(defects.shape[0]):
                        _, _, _, d = defects[i, 0]
                        if d > 1000:
                            defects_count += 1
        except Exception:
            defects_count = 0

        # Shape Classification & Confidence Scoring
        shape = "unknown"
        confidence = 0.50

        if circ >= 0.70 and solidity >= 0.82 and 0.75 <= aspect_ratio <= 1.30:
            shape = "circle"
            confidence = min(0.99, round(circ * 0.85 + solidity * 0.15, 2))
        elif num_v == 3 or (num_v <= 4 and solidity >= 0.65 and circ < 0.65 and defects_count <= 1):
            shape = "triangle"
            confidence = 0.95 if num_v == 3 else 0.82
        elif (num_v == 4 and solidity >= 0.85) or (extent >= 0.75 and solidity >= 0.85 and 0.70 <= aspect_ratio <= 1.40):
            shape = "rectangle"
            confidence = 0.95 if num_v == 4 else 0.85
        elif (circ < 0.45 and num_v >= 5) or (solidity < 0.65 and num_v >= 5) or (defects_count >= 3 and solidity < 0.70):
            shape = "star"
            confidence = 0.95 if (defects_count >= 3 or solidity < 0.55) else 0.88
        elif num_v == 6 or (circ >= 0.58 and solidity >= 0.78 and num_v in [5, 6, 7] and defects_count <= 2):
            shape = "hexagon"
            confidence = 0.92 if num_v == 6 else 0.82
        elif (num_v >= 8 and solidity < 0.72 and 0.75 <= aspect_ratio <= 1.30) or (defects_count >= 4 and 0.75 <= aspect_ratio <= 1.30):
            shape = "cross"
            confidence = 0.90

        return {
            "idx": idx,
            "shape": shape,
            "confidence": round(confidence, 2),
            "solidity": round(solidity, 3),
            "circularity": round(circ, 3),
            "vertices": num_v,
            "defects": defects_count,
            "aspect_ratio": aspect_ratio,
            "extent": extent,
            "area": round(area, 1)
        }
    except Exception as e:
        return {"idx": idx, "shape": "error", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": 0.0, "error": str(e)}

# -----------------------------------------------------------------------------
# Audio DSP & Speech-to-Text Logic
# -----------------------------------------------------------------------------
NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "for": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "ate": "8", "nine": "9",
    "to": "2", "too": "2", "tree": "3", "won": "1", "ten": "10"
}

def extract_digits(text: str) -> str:
    """Extract sequence of numbers from spoken or raw transcript."""
    digits_direct = re.sub(r'[^0-9]', '', text)
    if digits_direct:
        return digits_direct

    words = text.lower().split()
    digits = []
    for w in words:
        cw = re.sub(r'[^a-z]', '', w)
        if cw in NUMBER_WORDS:
            digits.append(NUMBER_WORDS[cw])
    return "".join(digits)

def process_audio_payload(audio_bytes: bytes, language: str = "en-US", apply_dsp: bool = True, whisper_model: str = "tiny.en") -> tuple:
    """Filter noise via DSP and transcribe via Whisper or Google Speech."""
    import tempfile
    import speech_recognition as sr
    from pydub import AudioSegment
    from pydub.effects import normalize

    # Load audio into AudioSegment
    audio_seg = AudioSegment.from_file(io.BytesIO(audio_bytes))

    if apply_dsp:
        try:
            # Bandpass filter (voice frequency 300Hz - 3400Hz) & normalize
            audio_seg = audio_seg.high_pass_filter(300).low_pass_filter(3400)
            audio_seg = normalize(audio_seg)
        except Exception:
            pass

    wav_io = io.BytesIO()
    audio_seg.export(wav_io, format="wav")
    wav_bytes = wav_io.getvalue()

    raw_text = ""
    engine_used = "google_speech_api"

    # Attempt 1: Local Whisper if available
    whisper_engine = get_whisper(whisper_model)
    if whisper_engine is not None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        try:
            res = whisper_engine.transcribe(tmp_path, language="en", fp16=False)
            raw_text = res.get("text", "").strip()
            engine_used = f"whisper_{whisper_model}"
        except Exception as e:
            print(f"[!] Whisper transcription failed: {e}, falling back to Google Speech", flush=True)
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    # Attempt 2: Google Speech Recognition Fallback
    if not raw_text:
        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio_data = recognizer.record(source)
            raw_text = recognizer.recognize_google(audio_data, language=language)
            engine_used = "google_speech_api"
        except sr.UnknownValueError:
            raw_text = ""
        except Exception as e:
            raw_text = ""

    clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', raw_text).strip().lower()
    digit_text = extract_digits(raw_text)

    return clean_text, digit_text, raw_text, engine_used

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@app.get("/")
def root():
    ram_mb = get_ram_mb()
    return {
        "service": "Link4M Bypass Suite Centralized API",
        "status": "online",
        "version": "2.5.0",
        "ram_used_mb": ram_mb,
        "docs_url": "/docs"
    }

@app.get("/health")
def health():
    ram_mb = get_ram_mb()
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "ram_used_mb": ram_mb,
        "safe_limit": ram_mb < 450.0,
        "models_cached": {
            "rapidocr": _OCR_ENGINE is not None,
            "whisper": _WHISPER_MODEL is not None
        }
    }

@app.get("/api/v1/status")
def status():
    ram_mb = get_ram_mb()
    return {
        "process_ram_mb": ram_mb,
        "total_requests": _REQUEST_COUNTER,
        "models": {
            "rapidocr_loaded": _OCR_ENGINE is not None,
            "whisper_loaded": _WHISPER_MODEL is not None
        },
        "python": sys.version.split()[0],
        "system_status": "STABLE_24_7"
    }

# 1. OCR RESOLVE DOMAIN & DE-OBFUSCATION
@app.post("/api/v1/ocr/resolve-domain", response_model=OcrResponse)
def ocr_resolve_domain(req: OcrRequest):
    t0 = time.perf_counter()
    check_and_gc()

    image_bytes = None
    if req.image_base64:
        try:
            image_bytes = base64.b64decode(req.image_base64.split(",")[-1])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")
    elif req.image_url:
        try:
            resp = _HTTP.get(req.image_url, timeout=8, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://linkhuongdan.online/"})
            if resp.status_code == 200:
                image_bytes = resp.content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image URL: {e}")
    else:
        raise HTTPException(status_code=400, detail="Provide image_url or image_base64")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image data")

    image_bytes = safe_downscale_image(image_bytes, max_dim=1280)
    engine = get_rapidocr()
    lines, _ = engine(image_bytes)
    domains, raw_text = extract_domains_from_text(lines)

    elapsed = (time.perf_counter() - t0) * 1000
    return OcrResponse(
        domains=domains,
        raw_text=raw_text,
        elapsed_ms=round(elapsed, 2),
        ram_used_mb=get_ram_mb()
    )

@app.post("/api/v1/ocr/upload")
async def ocr_upload(file: UploadFile = File(...)):
    t0 = time.perf_counter()
    check_and_gc()

    image_bytes = await file.read()
    image_bytes = safe_downscale_image(image_bytes, max_dim=1280)

    engine = get_rapidocr()
    lines, _ = engine(image_bytes)
    domains, raw_text = extract_domains_from_text(lines)

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "filename": file.filename,
        "domains": domains,
        "raw_text": raw_text,
        "elapsed_ms": round(elapsed, 2),
        "ram_used_mb": get_ram_mb()
    }

# 2. QCAPTCHA TILE GEOMETRIC CV SOLVER
@app.post("/api/v1/cv/analyze-tiles")
def analyze_tiles(req: TileAnalyzeRequest):
    t0 = time.perf_counter()
    check_and_gc()

    items = []
    if req.tiles:
        items = [(t.idx, t.url) for t in req.tiles]
    elif req.tile_urls:
        items = [(i, u) for i, u in enumerate(req.tile_urls)]
    else:
        raise HTTPException(status_code=400, detail="Provide tiles or tile_urls")

    futures = [_THREAD_POOL.submit(analyze_single_tile, idx, url) for idx, url in items]
    results = [f.result() for f in futures]
    results.sort(key=lambda x: x["idx"])

    correct_indices = []
    confidence_map = {}
    target = req.target_shape.strip().lower() if req.target_shape else None

    for r in results:
        idx = r["idx"]
        conf = r.get("confidence", 0.0)
        confidence_map[str(idx)] = conf

        if target and r.get("shape") == target and conf >= req.min_confidence:
            correct_indices.append(idx)

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "target_shape": req.target_shape,
        "correct_indices": correct_indices,
        "confidence_map": confidence_map,
        "tiles": results,
        "elapsed_ms": round(elapsed, 2),
        "ram_used_mb": get_ram_mb()
    }

# 3. RECAPTCHA AUDIO TRANSCRIBE & DSP ENHANCER
@app.post("/api/v1/audio/transcribe")
def audio_transcribe(req: AudioTranscribeRequest):
    t0 = time.perf_counter()
    check_and_gc()

    audio_bytes = None
    if req.audio_base64:
        try:
            audio_bytes = base64.b64decode(req.audio_base64.split(",")[-1])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {e}")
    elif req.audio_url:
        try:
            resp = _HTTP.get(req.audio_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                audio_bytes = resp.content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch audio from URL: {e}")
    else:
        raise HTTPException(status_code=400, detail="Provide audio_url or audio_base64")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    clean_text, digit_text, raw_text, engine_used = process_audio_payload(
        audio_bytes=audio_bytes,
        language=req.language,
        apply_dsp=req.apply_dsp_filter,
        whisper_model=req.model
    )

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "text": clean_text,
        "digit_text": digit_text,
        "raw_text": raw_text,
        "engine": engine_used,
        "elapsed_ms": round(elapsed, 2),
        "ram_used_mb": get_ram_mb()
    }

# 4. FAST LINK DECODER & PARAMETER UNPACKER
@app.post("/api/v1/link/decode")
def decode_link(req: DecodeLinkRequest):
    t0 = time.perf_counter()
    url = req.url.strip()
    decoded = None
    next_hop = None

    if '/go/file/' in url:
        part = url.split('/go/file/')[-1].split('?')[0].split('#')[0]
        try:
            dec = base64.b64decode(part + '===').decode('utf-8')
            if dec.startswith('http'):
                decoded = dec
        except Exception:
            pass

        if not decoded:
            try:
                dec = urllib.parse.unquote(part)
                if dec.startswith('http'):
                    decoded = dec
            except Exception:
                pass
    else:
        try:
            dec = base64.b64decode(url + '===').decode('utf-8')
            if dec.startswith('http'):
                decoded = dec
        except Exception:
            pass

    target_url = decoded or url
    if req.follow_redirects and target_url.startswith('http'):
        try:
            r = _HTTP.get(target_url, allow_redirects=False, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code in (301, 302, 303, 307, 308):
                next_hop = r.headers.get('Location')
        except Exception:
            pass

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "input_url": url,
        "decoded_url": decoded,
        "next_hop": next_hop,
        "final_candidate": next_hop or decoded or url,
        "elapsed_ms": round(elapsed, 2),
        "ram_used_mb": get_ram_mb()
    }

# 5. CLOUDFLARE TURNSTILE AUTOMATED SOLVER
@app.post("/api/v1/turnstile/solve")
async def turnstile_solve(req: TurnstileSolveRequest):
    try:
        from src.core.turnstile_solver import TurnstileSolver
    except ImportError:
        try:
            from turnstile_solver import TurnstileSolver
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"Turnstile solver module not found: {e}")

    t0 = time.perf_counter()
    timeout = req.timeout_seconds or 30

    def _run_solve():
        solver = TurnstileSolver(headless=req.headless)
        return solver.solve(url=req.url, sitekey=req.sitekey)

    try:
        result = await asyncio.get_event_loop().run_in_executor(_THREAD_POOL, _run_solve)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Turnstile solver execution failed: {e}")

    elapsed = round(time.perf_counter() - t0, 2)
    token = result.get("token") if isinstance(result, dict) else None

    if not token:
        raise HTTPException(status_code=504, detail="Turnstile solver timeout or token not retrieved")

    return {
        "status": "success",
        "token": token,
        "elapsed_seconds": elapsed,
        "engine": "patchright_playwright"
    }

# -----------------------------------------------------------------------------
# Server Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[*] Starting Link4M Bypass Suite Microservice API on port {port}...")
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)
