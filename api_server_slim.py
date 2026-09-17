#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
⚡ LINK4M ULTRA-SLIM & TURBO MICROSERVICE API (SUB-0.1S OPTIMIZED) ⚡
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
import hashlib
import urllib.request
import urllib.parse
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")
CORE_DIR = os.path.join(SRC_DIR, "core")
for p in [CURRENT_DIR, SRC_DIR, CORE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import numpy as np
import cv2
import speech_recognition as sr
from pydub import AudioSegment
from pydub.effects import normalize, high_pass_filter, low_pass_filter
import psutil

os.environ["MALLOC_ARENA_MAX"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

_REQUEST_COUNTER = 0
_PROCESS = psutil.Process(os.getpid())
_OCR_ENGINE = None
_THREAD_POOL = ThreadPoolExecutor(max_workers=16)

_TILE_CACHE: Dict[str, dict] = {}
_MAX_TILE_CACHE = 800
_OCR_CACHE: Dict[str, dict] = {}
_MAX_OCR_CACHE = 400
_K3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

_HTTP = requests.Session()
_retries = Retry(total=2, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=_retries, pool_connections=20, pool_maxsize=20)
_HTTP.mount("https://", _adapter)
_HTTP.mount("http://", _adapter)

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

def get_rapidocr():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR(use_angle_cls=False, det_limit_side_len=320, det_db_box_thresh=0.3, det_db_unclip_ratio=1.5)
        # Pre-warm
        dummy = np.full((60, 200, 3), 255, dtype=np.uint8)
        _, _ = _OCR_ENGINE(dummy)
    return _OCR_ENGINE

def get_ram_mb() -> float:
    try:
        return round(_PROCESS.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return 0.0

def check_and_gc():
    global _REQUEST_COUNTER
    _REQUEST_COUNTER += 1
    if _REQUEST_COUNTER % 40 == 0:
        gc.collect()

# -----------------------------------------------------------------------------
# FastAPI App
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Link4M Ultra-Slim Turbo API",
    description="Engineered for high stability and sub-0.1s response on containers.",
    version="3.1.0-slim-turbo"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    try:
        _THREAD_POOL.submit(get_rapidocr)
    except Exception:
        pass

class OcrRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    filter_traffic_widgets: bool = False

class OcrResponse(BaseModel):
    domains: List[str]
    raw_text: List[str]
    elapsed_ms: float
    ram_used_mb: float
    cached: bool = False

class TileItem(BaseModel):
    idx: int
    url: Optional[str] = None
    base64_data: Optional[str] = None

class TileAnalyzeRequest(BaseModel):
    tiles: Optional[List[TileItem]] = None
    tile_urls: Optional[List[str]] = None
    tile_base64s: Optional[List[str]] = None
    target_shape: Optional[str] = None
    min_confidence: float = 0.55

class AudioTranscribeRequest(BaseModel):
    audio_url: Optional[str] = None
    audio_base64: Optional[str] = None
    language: str = "en-US"
    apply_dsp_filter: bool = True

class DecodeLinkRequest(BaseModel):
    url: str
    follow_redirects: bool = True

class TurnstileSolveRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL")
    sitekey: str = Field(..., description="Turnstile sitekey")
    headless: bool = Field(True, description="Headless browser mode")
    timeout_seconds: Optional[int] = Field(30, alias="timeout_sec")
    worker_url: Optional[str] = None

IGNORE_DOMAINS = {
    'google.com', 'google.com.vn', 'shopee.vn', 'youtube.com', 'facebook.com',
    'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'wikipedia.org',
    'scholar.google.com', 't.me', 'telegram.org', 'linkhuongdan.online', 'octolink.vip',
    'play.google.com', 'mudeo.app', 'apps.apple.com', 'placehold.co'
}
JUNK_EXT = ('.app', '.play', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif')
RE_DOMAIN = re.compile(r'(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)')
RE_DOT = re.compile(r'\[dot\]|\(dot\)|\{dot\}|\s+dot\s+|\[\.\]|\(\.\)|_dot_', re.IGNORECASE)

def extract_domains(lines: list) -> tuple:
    candidates = []
    raw_texts = []
    if not lines:
        return candidates, raw_texts
    for item in lines:
        text = item[1].strip()
        raw_texts.append(text)
        norm = RE_DOT.sub('.', text)
        for part in norm.split():
            clean = part.strip('()[]{}<>,;:\'\" \t\r\n')
            match = RE_DOMAIN.search(clean)
            if match:
                d = match.group(1).lower().strip('.')
                if d in IGNORE_DOMAINS or any(d.endswith(ext) for ext in JUNK_EXT):
                    continue
                if d not in candidates:
                    candidates.append(d)
    return candidates, raw_texts

def analyze_tile_raw(idx: int, raw_bytes: bytes) -> dict:
    h = hashlib.md5(raw_bytes).hexdigest()
    if h in _TILE_CACHE:
        res = dict(_TILE_CACHE[h])
        res["idx"] = idx
        res["cached"] = True
        return res

    try:
        arr = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return {"idx": idx, "shape": "blank", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": 0.0}

        hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 1] > 28) | (hsv[:, :, 2] < 160)).astype(np.uint8) * 255
        mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _K3)
        contours, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            out = {"idx": idx, "shape": "blank", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": 0.0}
            if len(_TILE_CACHE) < _MAX_TILE_CACHE: _TILE_CACHE[h] = out
            return out

        c = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(c))
        peri = float(cv2.arcLength(c, True))
        if area < 30 or peri == 0:
            out = {"idx": idx, "shape": "blank", "confidence": 0.0, "solidity": 0.0, "circularity": 0.0, "vertices": 0, "defects": 0, "aspect_ratio": 0.0, "extent": 0.0, "area": area}
            if len(_TILE_CACHE) < _MAX_TILE_CACHE: _TILE_CACHE[h] = out
            return out

        circ = (4.0 * np.pi * area) / (peri * peri)
        hull = cv2.convexHull(c)
        hull_area = float(cv2.contourArea(hull))
        solidity = (area / hull_area) if hull_area > 0 else 0.0

        approx = cv2.approxPolyDP(c, 0.032 * peri, True)
        num_v = len(approx)

        x, y, w, h_box = cv2.boundingRect(c)
        aspect_ratio = round(float(min(w, h_box)) / max(w, h_box), 2) if max(w, h_box) > 0 else 0.0
        extent = round(area / (w * h_box), 2) if (w * h_box) > 0 else 0.0

        defects_count = 0
        try:
            hull_idx = cv2.convexHull(c, returnPoints=False)
            if len(hull_idx) > 3 and len(c) > 3:
                defects = cv2.convexityDefects(c, hull_idx)
                if defects is not None:
                    min_dim = min(w, h_box)
                    for i in range(defects.shape[0]):
                        _, _, _, d = defects[i, 0]
                        if (d / 256.0) > (min_dim * 0.12):
                            defects_count += 1
        except Exception:
            defects_count = 0

        shape = "unknown"
        confidence = 0.50

        if (defects_count == 4 and solidity > 0.63) or (num_v in (11, 12) and 0.60 <= solidity <= 0.80):
            shape = "cross"
            confidence = 0.96
        elif defects_count >= 5 or (solidity <= 0.63 and circ < 0.48) or (num_v == 10 and solidity < 0.65):
            shape = "star"
            confidence = 0.98 if defects_count >= 5 else 0.90
        elif num_v == 3 or (solidity >= 0.84 and circ <= 0.69 and num_v <= 5 and 0.35 <= extent <= 0.68):
            shape = "triangle"
            confidence = 0.98 if num_v == 3 else 0.88
        elif num_v == 4 and solidity >= 0.88 and extent >= 0.70:
            shape = "rectangle"
            confidence = 0.96
        elif num_v in (5, 6, 7) and solidity >= 0.88 and 0.68 <= circ <= 0.86 and aspect_ratio >= 0.72:
            shape = "hexagon"
            confidence = 0.96 if num_v == 6 else 0.85
        elif solidity >= 0.90 and (circ >= 0.86 or (circ >= 0.80 and num_v >= 8)) and aspect_ratio >= 0.74:
            shape = "circle"
            confidence = min(0.99, round((circ / 0.88) * 0.95, 2))
        elif defects_count >= 3 and solidity <= 0.75:
            shape = "cross" if solidity > 0.62 else "star"
            confidence = 0.80

        out = {
            "idx": idx,
            "shape": shape,
            "confidence": confidence,
            "solidity": round(solidity, 3),
            "circularity": round(circ, 3),
            "vertices": num_v,
            "defects": defects_count,
            "aspect_ratio": aspect_ratio,
            "extent": extent,
            "area": round(area, 1)
        }
        if len(_TILE_CACHE) < _MAX_TILE_CACHE:
            _TILE_CACHE[h] = out
        return out
    except Exception as e:
        return {"idx": idx, "shape": "error", "confidence": 0.0, "error": str(e)}

def fetch_and_analyze_tile(args: tuple) -> dict:
    idx, item = args
    if isinstance(item, str):
        if item.startswith("data:image") or len(item) > 300:
            try:
                raw_bytes = base64.b64decode(item.split(",")[-1])
                return analyze_tile_raw(idx, raw_bytes)
            except Exception as e:
                return {"idx": idx, "shape": "decode_error", "confidence": 0.0, "error": str(e)}
        url = item
        if url.startswith('/'):
            url = 'https://frame.103-141-140-153.sslip.io' + url
        try:
            resp = _HTTP.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return analyze_tile_raw(idx, resp.content)
            return {"idx": idx, "shape": "http_error", "confidence": 0.0}
        except Exception as e:
            return {"idx": idx, "shape": "error", "confidence": 0.0, "error": str(e)}
    return {"idx": idx, "shape": "unknown", "confidence": 0.0}

DIGIT_WORDS = {
    'zero': '0', 'oh': '0', 'o': '0', 'hero': '0', 'null': '0',
    'one': '1', 'won': '1', 'wan': '1',
    'two': '2', 'to': '2', 'too': '2', 'tu': '2',
    'three': '3', 'tree': '3', 'free': '3',
    'four': '4', 'for': '4', 'fore': '4', 'fo': '4', 'floor': '4',
    'five': '5', 'fiv': '5', 'hive': '5', 'fine': '5',
    'six': '6', 'sex': '6', 'sicks': '6', 'sax': '6', 'fix': '6',
    'seven': '7', 'sever': '7', 'heaven': '7',
    'eight': '8', 'ate': '8', 'ait': '8', 'hate': '8', 'weight': '8',
    'nine': '9', 'mine': '9', 'line': '9', 'nigh': '9'
}

def extract_digits(text: str) -> str:
    digits_direct = re.sub(r'[^0-9]', '', text)
    if digits_direct:
        return digits_direct
    tokens = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    digits = []
    for tok in tokens:
        if tok.isdigit():
            digits.append(tok)
        elif tok in DIGIT_WORDS:
            digits.append(DIGIT_WORDS[tok])
    return "".join(digits)

@app.get("/")
def root():
    return {
        "service": "Link4M Ultra-Slim Turbo API",
        "status": "online",
        "latency_target": "<0.1s",
        "ram_used_mb": get_ram_mb(),
        "docs": "/docs"
    }

@app.get("/health")
def health():
    ram_mb = get_ram_mb()
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "ram_used_mb": ram_mb,
        "safe_limit": ram_mb < 380.0,
        "cached_tiles": len(_TILE_CACHE),
        "cached_ocr": len(_OCR_CACHE)
    }

@app.get("/api/v1/status")
def status():
    ram_mb = get_ram_mb()
    return {
        "process_ram_mb": ram_mb,
        "total_requests": _REQUEST_COUNTER,
        "ocr_loaded": _OCR_ENGINE is not None,
        "system_status": "STABLE_TURBO_24_7"
    }

@app.post("/api/v1/ocr/resolve-domain", response_model=OcrResponse)
def ocr_resolve_domain(req: OcrRequest):
    t0 = time.perf_counter()
    check_and_gc()

    image_bytes = None
    if req.image_base64:
        try:
            image_bytes = base64.b64decode(req.image_base64.split(",")[-1])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")
    elif req.image_url:
        try:
            resp = _HTTP.get(req.image_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                image_bytes = resp.content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image: {e}")
    else:
        raise HTTPException(status_code=400, detail="Missing image_url or image_base64")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image data")

    h = hashlib.md5(image_bytes).hexdigest()
    if h in _OCR_CACHE:
        cached = _OCR_CACHE[h]
        elapsed = (time.perf_counter() - t0) * 1000
        return OcrResponse(
            domains=cached["domains"],
            raw_text=cached["raw_text"],
            elapsed_ms=round(elapsed, 2),
            ram_used_mb=get_ram_mb(),
            cached=True
        )

    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(status_code=400, detail="Corrupted image bytes")

    h_img, w_img = arr.shape[:2]
    if max(h_img, w_img) > 480:
        scale = 480.0 / max(h_img, w_img)
        arr = cv2.resize(arr, (int(w_img * scale), int(h_img * scale)), interpolation=cv2.INTER_AREA)

    engine = get_rapidocr()
    lines, _ = engine(arr)
    domains, raw_text = extract_domains(lines)

    if len(_OCR_CACHE) < _MAX_OCR_CACHE:
        _OCR_CACHE[h] = {"domains": domains, "raw_text": raw_text}

    elapsed = (time.perf_counter() - t0) * 1000
    return OcrResponse(
        domains=domains,
        raw_text=raw_text,
        elapsed_ms=round(elapsed, 2),
        ram_used_mb=get_ram_mb(),
        cached=False
    )

@app.post("/api/v1/cv/analyze-tiles")
def analyze_tiles(req: TileAnalyzeRequest):
    t0 = time.perf_counter()
    check_and_gc()

    items = []
    if req.tiles:
        for t in req.tiles:
            items.append((t.idx, t.url or t.base64_data))
    elif req.tile_urls:
        items = [(i, u) for i, u in enumerate(req.tile_urls)]
    elif req.tile_base64s:
        items = [(i, b) for i, b in enumerate(req.tile_base64s)]
    else:
        raise HTTPException(status_code=400, detail="Provide tiles, tile_urls, or tile_base64s")

    futures = [_THREAD_POOL.submit(fetch_and_analyze_tile, item) for item in items]
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

@app.post("/api/v1/audio/transcribe")
def audio_transcribe(req: AudioTranscribeRequest):
    t0 = time.perf_counter()
    check_and_gc()

    audio_bytes = None
    if req.audio_base64:
        try:
            audio_bytes = base64.b64decode(req.audio_base64.split(",")[-1])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")
    elif req.audio_url:
        try:
            resp = _HTTP.get(req.audio_url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                audio_bytes = resp.content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to download audio: {e}")
    else:
        raise HTTPException(status_code=400, detail="Provide audio_url or audio_base64")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    try:
        audio_seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        if req.apply_dsp_filter:
            audio_seg = normalize(audio_seg)
            audio_seg = high_pass_filter(audio_seg, 250)
            audio_seg = low_pass_filter(audio_seg, 3500)

        wav_io = io.BytesIO()
        audio_seg.export(wav_io, format="wav")
        wav_io.seek(0)

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data, language=req.language)
        clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip().lower()
        digit_text = extract_digits(text)
    except sr.UnknownValueError:
        clean_text = ""
        digit_text = ""
        text = ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speech recognition error: {e}")

    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "text": clean_text,
        "digit_text": digit_text,
        "raw_text": text,
        "engine": "google_speech_api_v2_slim",
        "elapsed_ms": round(elapsed, 2),
        "ram_used_mb": get_ram_mb()
    }

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
            r = _HTTP.get(target_url, allow_redirects=False, timeout=3, headers={'User-Agent': 'Mozilla/5.0'})
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

    def _run_solve():
        solver = TurnstileSolver(headless=req.headless)
        return solver.solve(url=req.url, sitekey=req.sitekey, use_cloud=False)

    try:
        result = await asyncio.get_event_loop().run_in_executor(_THREAD_POOL, _run_solve)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Turnstile solver execution failed: {e}")

    elapsed = round(time.perf_counter() - t0, 2)
    token = result.get("token") or result.get("turnstile_value") if isinstance(result, dict) else None

    if not token:
        raise HTTPException(status_code=504, detail="Turnstile solver timeout or token not retrieved")

    return {
        "status": "success",
        "token": token,
        "elapsed_seconds": elapsed,
        "engine": "patchright_playwright"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[*] Starting Link4M Ultra-Slim Turbo API on port {port}...")
    uvicorn.run("api_server_slim:app", host="0.0.0.0", port=port, reload=False)
