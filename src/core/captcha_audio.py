#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Giải reCAPTCHA v2 qua kênh AUDIO (nút tai nghe) — không cần API trả tiền.

Vì sao dùng đường này: reCAPTCHA v2 luôn có kênh trợ năng cho người khiếm thị —
nút tai nghe đọc vài từ tiếng Anh. Chép lời bằng model nhỏ chạy tại máy, điền
vào ô trả lời, thế là xong. Không credit, không key, không gửi ảnh đi đâu.

Bậc thang nhận dạng (tự hạ cấp khi cái trên không có):
    1. faster-whisper (int8, CPU) — model đã cache sẵn ở ~/.cache/huggingface
    2. vosk — nếu có model trong VOSK_MODEL hoặc ~/.cache/vosk
    3. Google Web Speech qua HTTPS — không key, chỉ cần WAV 16k mono

Ghép vào engine:
    from captcha_audio import solve
    tok = solve(page)          # "" nếu thua, token nếu thắng
"""
from __future__ import annotations

import base64
import os
import subprocess
import time

AUDIO_FILE = "/tmp/rc_audio.mp3"
MODEL_SIZE = os.environ.get("RC_WHISPER_MODEL", "tiny.en")
# endpoint Web Speech công khai mà thư viện SpeechRecognition vẫn dùng
GOOGLE_STT = ("https://www.google.com/speech-api/v2/recognize"
              "?output=json&lang=en-US&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXxWjig")

_MODEL = None


def log(*a):
    try:
        from link4m_engine import log as _l
        _l(*a)
    except Exception:
        print("[audio]", *a, flush=True)


# ------------------------------------------------------------------ frame/DOM
def find_challenge(pg):
    """Trả frame bframe đang hiện thử thách (lưới ảnh hoặc ô audio)."""
    for f in pg.frames:
        if "bframe" not in f.url:
            continue
        try:
            if f.locator("#rc-imageselect-target, #rc-audiochallenge-response-field").count():
                return f
        except Exception:
            pass
    return None


def token_now(pg) -> str:
    try:
        vals = pg.evaluate("Array.from(document.querySelectorAll("
                           "'textarea[name=g-recaptcha-response]')).map(t=>t.value)")
    except Exception:
        return ""
    return max(vals, key=len) if vals else ""


def audio_ready(ch) -> bool:
    try:
        return bool(ch.locator("#audio-response").count())
    except Exception:
        return False


def _bframes(pg):
    try:
        return [f for f in pg.frames if "bframe" in (f.url or "")]
    except Exception:
        return []


def find_audio_frame(pg):
    """Frame đang có ô trả lời audio. Sau khi đổi chế độ, bframe có thể bị
    thay bằng frame mới nên phải dò lại chứ không giữ tham chiếu cũ."""
    for f in _bframes(pg):
        if audio_ready(f):
            return f
    return None


def open_audio_mode(ch, pg=None) -> bool:
    """Bấm nút tai nghe để đổi từ lưới ảnh sang thử thách audio.

    Nút có thể nằm ở frame khác frame đang giữ thử thách (anchor/challenge),
    nên dò toàn bộ bframe của page, không chỉ đúng frame truyền vào.
    """
    pg = pg or getattr(ch, "page", None)
    if audio_ready(ch):
        return True
    cands = [ch] + [f for f in _bframes(pg) if f is not ch] if pg else [ch]
    for f in cands:
        clicked = False
        for sel in ("#recaptcha-audio-button", "button#recaptcha-audio-button"):
            try:
                loc = f.locator(sel).first
                if loc.count():
                    loc.click(timeout=4000)
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            try:
                f.evaluate("() => { const b=document.getElementById('recaptcha-audio-button');"
                           " if (b) b.click(); }")
                clicked = True
            except Exception:
                pass
        if not clicked:
            continue
        for _ in range(16):
            time.sleep(0.5)
            if audio_ready(f):
                return True
            if pg and find_audio_frame(pg):
                return True
    return audio_ready(ch)


def fetch_audio(ch) -> bytes:
    """Lấy mp3 ngay trong frame (cùng origin google.com) để khỏi vướng CORS."""
    js = """async () => {
        const a = document.querySelector('#audio-source') ||
                  document.querySelector('audio');
        let src = a ? a.src : '';
        if (!src) {
            const dl = document.querySelector('.rc-audiochallenge-tdownload-link');
            src = dl ? dl.href : '';
        }
        if (!src) return '';
        const r = await fetch(src, {credentials:'omit'});
        if (!r.ok) return 'ERR' + r.status;
        const buf = await r.arrayBuffer();
        let bin = '';
        const b = new Uint8Array(buf);
        for (let i = 0; i < b.length; i++) bin += String.fromCharCode(b[i]);
        return btoa(bin);
    }"""
    for _ in range(3):
        try:
            data = ch.evaluate(js)
        except Exception:
            data = ""
        if data and not data.startswith("ERR"):
            try:
                return base64.b64decode(data)
            except Exception:
                pass
        if data.startswith("ERR"):
            log("[audio] tải mp3 lỗi:", data)
        time.sleep(1)
    return b""


# ------------------------------------------------------------------ nhận dạng
def _fw_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8",
                              cpu_threads=2, num_workers=1)
        log(f"[audio] whisper {MODEL_SIZE} đã nạp")
    return _MODEL


def _raw16k(path: str) -> bytes:
    """Giải mã về PCM 16k mono bằng sox (nhanh, nhẹ, khỏi đụng tới PyAV)."""
    raw = "/tmp/rc_audio.raw"
    subprocess.run(["sox", path, "-r", "16000", "-c", "1", "-e", "signed", "-b", "16",
                    "-t", "raw", raw], check=True, capture_output=True, timeout=60)
    return open(raw, "rb").read()


def transcribe_whisper(path: str) -> str:
    """faster-whisper bản mới gọi av.open(metadata_errors=...) mà PyAV 19 không có,
    nên tự giải mã bằng sox rồi đưa mảng float32 thẳng vào model."""
    import numpy as np
    data = _raw16k(path)
    if len(data) < 3200:          # ngắn hơn 0.1s thì bỏ
        return ""
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = _fw_model().transcribe(audio, language="en", beam_size=1,
                                     condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segs).strip()


def transcribe_vosk(path: str) -> str:
    import json
    import wave
    from vosk import KaldiRecognizer, Model, SetLogLevel
    mpath = os.environ.get("VOSK_MODEL") or os.path.expanduser("~/.cache/vosk/vosk-model-small-en-us-0.15")
    if not os.path.isdir(mpath):
        raise FileNotFoundError(mpath)
    wav = "/tmp/rc_audio.wav"
    subprocess.run(["sox", path, "-r", "16000", "-c", "1", "-e", "signed", "-b", "16", wav],
                   check=True, capture_output=True, timeout=60)
    SetLogLevel(-1)
    rec = KaldiRecognizer(Model(mpath), 16000)
    with wave.open(wav, "rb") as w:
        while True:
            d = w.readframes(4000)
            if not d:
                break
            rec.AcceptWaveform(d)
    return json.loads(rec.FinalResult()).get("text", "").strip()


def transcribe_google(path: str) -> str:
    """Kênh dự phòng: Web Speech công khai, cần WAV 16k mono."""
    import json
    import urllib.request
    wav = "/tmp/rc_audio.wav"
    raw = wav + ".raw"
    subprocess.run(["sox", path, "-r", "16000", "-c", "1", "-e", "signed", "-b", "16", raw],
                   check=True, capture_output=True, timeout=60)
    data = open(raw, "rb").read()
    if len(data) < 4000:
        return ""
    req = urllib.request.Request(GOOGLE_STT, data=data,
                                 headers={"Content-Type": "audio/l16; rate=16000"})
    body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    for line in body.splitlines():
        if not line.strip():
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue
        for alt in j.get("result", [{}])[0].get("alternative", []):
            t = alt.get("transcript", "").strip()
            if t:
                return t
    return ""


def transcribe(path: str) -> str:
    for name, fn in (("whisper", transcribe_whisper), ("vosk", transcribe_vosk)):
        try:
            t = fn(path)
            if t:
                log(f"[audio] {name}: {t}")
                return t
            log(f"[audio] {name}: rỗng")
        except Exception as e:
            log(f"[audio] {name} lỗi:", str(e)[:70])
    return ""


# ------------------------------------------------------------------ vòng giải
def error_text(ch) -> str:
    try:
        el = ch.locator(".rc-audiochallenge-error-message").first
        return (el.inner_text() or "").strip() if el.count() else ""
    except Exception:
        return ""


def solve(pg, tries: int = 4, limit: int = 150) -> str:
    """Giải thử thách đang hiện bằng audio; trả token ("" nếu thua)."""
    ch = find_challenge(pg) or find_audio_frame(pg)
    if not ch:
        return token_now(pg)
    for n in range(1, tries + 1):
        if not open_audio_mode(ch, pg):
            log("[audio] không mở được chế độ audio")
            return ""
        ch = find_audio_frame(pg) or find_challenge(pg) or ch
        blob = fetch_audio(ch)
        log(f"[audio] vòng {n}: mp3 {len(blob)} bytes")
        if not blob:
            return ""
        with open(AUDIO_FILE, "wb") as f:
            f.write(blob)
        text = transcribe(AUDIO_FILE)
        if not text:
            log("[audio] không chép được lời -> thử lại")
            _next_clip(ch)
            continue
        try:
            ch.locator("#audio-response").first.fill(text)
        except Exception:
            pass
        time.sleep(0.4)
        try:
            ch.locator("#recaptcha-verify-button").first.click(timeout=6000)
        except Exception:
            pass
        t0 = time.time()
        while time.time() - t0 < limit:
            time.sleep(1)
            tok = token_now(pg)
            if tok and not find_challenge(pg) and not find_audio_frame(pg):
                log(f"[audio] xong sau {int(time.time() - t0)}s, token {len(tok)}")
                return tok
            cur = find_audio_frame(pg) or find_challenge(pg)
            if cur is None:
                break
            err = error_text(cur)
            if err:
                low = err.lower()
                if "try again later" in low or "automated" in low or "blocked" in low:
                    log("[audio] bị chặn:", err[:70])
                    return ""
                if "multiple" in low or "thử" in low or "try again" in low:
                    log("[audio] cần vòng nữa:", err[:60])
                    break
                log("[audio] sai:", err[:60])
                break
        else:
            return token_now(pg)
    return token_now(pg)


def _next_clip(ch):
    """Xin clip khác: bấm lại nút tai nghe, hoặc bấm nút refresh của thử thách."""
    for sel in ("#recaptcha-reload-button", "#recaptcha-audio-button"):
        try:
            if ch.locator(sel).count():
                ch.locator(sel).first.click(timeout=4000)
                time.sleep(1.5)
                return
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    # kiểm tra nhanh khả năng chép lời: python captcha_audio.py <file_audio>
    if len(sys.argv) > 1:
        print(transcribe(sys.argv[1]))
    else:
        print("dùng: python captcha_audio.py <audio.mp3>")
