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

# reCAPTCHA đọc một chuỗi chữ số. ASR hay nghe nhầm thành từ đồng âm
# ("for" -> four, "to" -> two, "ate" -> eight); bảng này đổi lại.
DIGIT_WORDS = ["zero", "oh", "one", "two", "three", "four", "five",
               "six", "seven", "eight", "nine"]
_HOMOPHONES = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3", "tree": "3", "free": "3",
    "four": "4", "for": "4", "fore": "4",
    "five": "5",
    "six": "6", "sex": "6", "sicks": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9", "niner": "9",
}

_MODEL = None


def log(*a):
    try:
        from link4m_engine import log as _l
        _l(*a)
    except Exception:
        print("[audio]", *a, flush=True)


# ------------------------------------------------------------------ frame/DOM
def _on_screen(pg, frame) -> bool:
    """True khi iframe của bframe thật sự nằm trong viewport.

    reCAPTCHA tạo bframe cho **mọi** widget trên trang, kể cả widget bị ẩn
    (iframe đặt ở `top:-9999px`). Chọn nhầm frame ẩn thì lưới không có tile,
    không chụp được ảnh, và engine chờ index vô ích.
    """
    try:
        box = frame.frame_element().bounding_box()
    except Exception:
        return False
    if not box or box.get("width", 0) < 40 or box.get("height", 0) < 40:
        return False
    viewport = pg.viewport_size or {"width": 1280, "height": 800}
    top, bottom = box.get("y", 0), box.get("y", 0) + box.get("height", 0)
    return bottom > 0 and top < viewport.get("height", 800)


def find_challenge(pg):
    """Frame bframe của thử thách **đang hoạt động**.

    reCAPTCHA tạo một bframe cho mỗi widget trên trang, kể cả widget bị ẩn.
    Bframe ẩn chỉ có khung `#rc-imageselect-target` rỗng: chưa render tile và
    không có ô trả lời audio. Thử thách thật thì có tile (lưới) hoặc ô
    `#audio-response` (audio). Trong headless cửa sổ thử thách có thể nằm ngoài
    viewport, nên "trên màn hình" chỉ là điểm cộng — dấu hiệu quyết định là
    tile/ô audio.
    """
    ranked = []
    for f in pg.frames:
        if "bframe" not in (f.url or ""):
            continue
        try:
            has_grid = f.locator("#rc-imageselect-target").count()
            has_audio = f.locator("#rc-audiochallenge-response-field").count()
        except Exception:
            continue
        if not (has_grid or has_audio):
            continue
        tiles = 0
        try:
            tiles = f.locator("div.rc-imageselect-tile").count()
        except Exception:
            pass
        score = (4 if tiles else 0) + (4 if has_audio else 0) + (2 if _on_screen(pg, f) else 0)
        ranked.append((score, bool(tiles or has_audio), f))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    # Frame hoạt động (có tile hoặc ô audio) thắng ngay. Nếu chưa frame nào render
    # xong, vẫn nhận frame nằm trên màn hình: lưới ảnh cần vài trăm ms mới có tile,
    # và bỏ ở đây làm cả lượt captcha trượt (thấy ở lượt live 7).
    for _score, active, frame in ranked:
        if active:
            return frame
    best_score, _active, best_frame = ranked[0]
    return best_frame if best_score >= 2 else None


def token_now(pg) -> str:
    """Token của widget đang hiển thị; widget ẩn (nếu có) không được tính.

    Trang link4m gắn hai widget reCAPTCHA. Lấy token dài nhất trong mọi
    textarea sẽ trả token của widget kia, và form submit sẽ fail dù đã giải
    đúng.
    """
    try:
        entries = pg.evaluate("""() => Array.from(
            document.querySelectorAll('textarea[name=g-recaptcha-response]')
        ).map(t => {
            const host = t.closest('.g-recaptcha, [data-sitekey]');
            let visible = true;
            if (host) {
                const r = host.getBoundingClientRect();
                visible = r.width > 0 && r.height > 0 &&
                          r.bottom > 0 && r.top < (window.innerHeight || 800);
            }
            return {v: t.value || '', visible: visible};
        })""")
    except Exception:
        return ""
    if not entries:
        return ""
    visible = [e["v"] for e in entries if e.get("visible") and e.get("v")]
    if visible:
        return max(visible, key=len)
    if any(e.get("visible") for e in entries):
        # Có widget hiển thị nhưng chưa có token: đang chờ chính widget đó, không
        # được lấy token của widget ẩn khác trên cùng trang.
        return ""
    # Không widget nào nằm trong viewport (reCAPTCHA vô hình, badge ẩn): giữ
    # hành vi cũ — textarea dài nhất — thay vì trả rỗng và treo vòng chờ.
    everything = [e["v"] for e in entries if e.get("v")]
    return max(everything, key=len) if everything else ""


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


def transcribe_vosk(path: str, digits_only: bool = False) -> str:
    """Nhận dạng bằng Vosk; ``digits_only`` ép grammar chỉ còn chữ số.

    Clip reCAPTCHA là một chuỗi chữ số đọc trong tạp âm. Grammar tự do nghe
    thành câu vô nghĩa ("for eternity and so well"), còn grammar chữ số thu
    được đúng vài chữ số. Cả hai dạng đều được đem đi thử.
    """
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
    if digits_only:
        grammar = json.dumps(DIGIT_WORDS + ["[unk]"])
        rec = KaldiRecognizer(Model(mpath), 16000, grammar)
    else:
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


def digits_of(text: str) -> str:
    """Đổi câu ASR thành chuỗi chữ số ("for two" -> "42")."""
    import re
    out = []
    for word in re.findall(r"[a-z]+|\d+", (text or "").lower()):
        if word.isdigit():
            out.append(word)
        elif word in _HOMOPHONES:
            out.append(_HOMOPHONES[word])
    return "".join(out)


def _answer_candidates(path: str) -> list[str]:
    """Mọi câu trả lời đáng thử cho một clip, xếp theo độ tin cậy.

    Mỗi clip reCAPTCHA cho thử vài lần, nên thay vì nộp một câu rồi xin clip
    mới, ta nộp lần lượt các cách đọc khác nhau của **cùng** clip: bản whisper,
    bản vosk tự do, bản vosk grammar chữ số, và các bản đã chuẩn hoá đồng âm.
    """
    raw: list[str] = []
    for name, fn in (("whisper", transcribe_whisper),
                     ("vosk", transcribe_vosk),
                     ("vosk-digits", lambda p: transcribe_vosk(p, digits_only=True))):
        try:
            text = fn(path)
        except Exception as exc:
            log(f"[audio] {name} lỗi:", str(exc)[:70])
            continue
        text = (text or "").replace("[unk]", " ").strip()
        if text:
            log(f"[audio] {name}: {text}")
            raw.append(text)

    answers: list[str] = []
    for text in raw:
        answers.append(text)
    for text in raw:
        digits = digits_of(text)
        if 3 <= len(digits) <= 8:
            answers.append(digits)
    # Bản số trước bản chữ: reCAPTCHA chấp nhận cả hai, nhưng số ít lỗi chính tả.
    answers.sort(key=lambda a: (0 if a.isdigit() else 1, -len(a)))
    seen, unique = set(), []
    for a in answers:
        key = a.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def transcribe(path: str) -> str:
    """Câu trả lời tốt nhất cho một clip (rỗng nếu không đọc được gì)."""
    cands = _answer_candidates(path)
    return cands[0] if cands else ""


# ------------------------------------------------------------------ vòng giải
def error_text(ch) -> str:
    try:
        el = ch.locator(".rc-audiochallenge-error-message").first
        return (el.inner_text() or "").strip() if el.count() else ""
    except Exception:
        return ""


def _submit(ch, pg, answer: str, limit: int = 25) -> tuple[str, str]:
    """Nộp một đáp án và đọc phản hồi của reCAPTCHA.

    Trả ``(trạng_thái, token)`` với trạng thái:
    ``ok`` token đã có · ``blocked`` bị chặn/IP xấu · ``wrong`` sai ·
    ``advanced`` đúng (thử thách đổi sang clip khác) · ``timeout`` không rõ.
    """
    try:
        ch.locator("#audio-response").first.fill(answer)
    except Exception:
        return "timeout", ""
    time.sleep(0.4)
    try:
        ch.locator("#recaptcha-verify-button").first.click(timeout=6000)
    except Exception:
        return "timeout", ""
    t0 = time.time()
    while time.time() - t0 < limit:
        time.sleep(1)
        tok = token_now(pg)
        cur = find_audio_frame(pg) or find_challenge(pg)
        if tok and cur is None:
            log(f"[audio] '{answer}' đúng sau {int(time.time() - t0)}s, token {len(tok)}")
            return "ok", tok
        if cur is None:
            continue
        err = error_text(cur)
        if not err:
            continue
        low = err.lower()
        if "try again later" in low or "automated" in low or "blocked" in low:
            log("[audio] bị chặn:", err[:70])
            return "blocked", ""
        if "multiple" in low or "vài lần" in low or "try again" in low:
            log(f"[audio] '{answer}' sai, còn lượt:", err[:60])
            return "wrong", ""
        if "correct" in low or "chính xác" in low:
            return "advanced", ""
        log(f"[audio] '{answer}' sai:", err[:60])
        return "wrong", ""
    return "timeout", ""


def solve(pg, tries: int = 4, limit: int = 150) -> str:
    """Giải thử thách đang hiện bằng audio; trả token ("" nếu thua).

    ``tries`` là số clip tối đa, ``limit`` là ngân sách chờ tổng (giữ tham số
    cũ cho tương thích). Mỗi clip được nộp nhiều đáp án — ASR trên clip nhiễu
    thường đúng ở một cách đọc nào đó chứ hiếm khi đúng ngay bản đầu.
    """
    deadline = time.time() + max(limit, 30)
    ch = find_challenge(pg) or find_audio_frame(pg)
    if not ch:
        # Bframe mới render sau khi hộp kiểm được bấm; dò ngay lập tức hay trượt.
        for _ in range(12):
            time.sleep(0.5)
            ch = find_challenge(pg) or find_audio_frame(pg)
            if ch:
                break
    if not ch:
        log("[audio] không thấy bframe có thử thách")
        return token_now(pg)
    for n in range(1, tries + 1):
        if time.time() > deadline:
            log("[audio] hết ngân sách chờ")
            break
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
        candidates = _answer_candidates(AUDIO_FILE)
        if not candidates:
            log("[audio] không chép được lời -> clip khác")
            _next_clip(ch)
            continue
        log("[audio] đáp án thử:", " | ".join(candidates[:4]))
        advanced = False
        for answer in candidates[:4]:
            state, tok = _submit(ch, pg, answer)
            if state == "ok":
                return tok
            if state == "blocked":
                return ""
            if state == "advanced":
                advanced = True
                break
            ch = find_audio_frame(pg) or find_challenge(pg) or ch
        if not advanced:
            _next_clip(ch)
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
