#!/usr/bin/env python3
"""Local faster-whisper HTTP inference server for l4m-engine ASR_URL."""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from faster_whisper import WhisperModel

PORT = int(os.environ.get("ASR_PORT", "18089"))
MODEL_NAME = os.environ.get("ASR_MODEL", "tiny.en")
_MODEL = None
_MODEL_LOCK = threading.Lock()


def get_model() -> WhisperModel:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            try:
                _MODEL = WhisperModel(
                    MODEL_NAME, device="cpu", compute_type="int8", local_files_only=True
                )
            except Exception:
                _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        return _MODEL


def extract_wav(body: bytes) -> bytes:
    idx = body.find(b"RIFF")
    if idx == -1:
        return body
    end = body.find(b"\r\n--", idx)
    return body[idx:end] if end != -1 else body[idx:]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        out = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        wav = extract_wav(body)
        text = ""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            tmp_path = f.name
        try:
            segments, _ = get_model().transcribe(tmp_path, language="en", beam_size=1)
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            sys.stderr.write(f"ASR error: {e}\n")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        payload = json.dumps({"text": text}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=get_model, daemon=True).start()
    print(f"ASR_READY http://127.0.0.1:{PORT}/inference", flush=True)
    srv.serve_forever()
