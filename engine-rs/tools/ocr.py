#!/usr/bin/env python3
"""OCR sidecar for the campaign instruction images.

The instruction strip embeds the search keyword and the sponsor domain as
bitmap text, so the engine hands the decoded images to this helper and gets
plain lines back. RapidOCR runs on CPU with the bundled ONNX models; no
network access, no paid API.

Images are downscaled to 800 px before recognition: the source strips are
screenshots of large UI text, and the full-resolution pass costs ~3x more for
the same characters.

Two modes:

  ocr.py img1.png img2.png        one-shot, prints a JSON array of line blocks
  ocr.py --serve                  long-lived: JSON request per stdin line,
                                  JSON response per stdout line. Loading the
                                  ONNX models once is what makes a campaign
                                  discovery cheap on a slow box.
"""

import json
import os
import re
import sys
import time

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

MAX_WIDTH = 640
MAX_HEIGHT = int(os.environ.get("OCR_MAX_HEIGHT", "240") or 240)
_DOMAIN_URL_RE = re.compile(r"https?://([a-z0-9-]+(?:\.[a-z0-9-]+)+)", re.I)
_EXCLUDED_DOMAINS = (
    "google.",
    "facebook.",
    "youtube.",
    "link4m.",
    "gstatic.",
    "doubleclick.",
    "googletagmanager",
)


def _has_sponsor_url(lines: list[str]) -> bool:
    for line in lines:
        for m in _DOMAIN_URL_RE.finditer(line):
            host = m.group(1).lower()
            if not any(ex in host for ex in _EXCLUDED_DOMAINS):
                return True
    return False


def _scan_files(engine, files: list[str], pool=None) -> list[list[str]]:
    # Scan from the last strip backwards: Link4M puts the full sponsor URL
    # screenshot near the end (instr-3/instr-4), so stopping as soon as a
    # non-excluded URL is found avoids OCR-ing the earlier instruction strips.
    if len(files) > 1:
        collected: list[list[str]] = []
        for path in reversed(files):
            lines = read_lines(engine, path)
            collected.append(lines)
            if _has_sponsor_url(lines):
                collected.reverse()
                return collected
        collected.reverse()
        return collected
    if pool and len(files) > 1:
        return list(pool.map(lambda path: read_lines(engine, path), files))
    return [read_lines(engine, path) for path in files]


def read_lines(engine, path: str) -> list[str]:
    try:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        if w > MAX_WIDTH:
            h = int(h * MAX_WIDTH / w)
            w = MAX_WIDTH
            im = im.resize((w, h), Image.BILINEAR)
        if MAX_HEIGHT > 0 and h > MAX_HEIGHT:
            im = im.crop((0, 0, w, MAX_HEIGHT))
        result, _ = engine(np.asarray(im))
        return [line[1] for line in (result or [])]
    except Exception:
        return []


def serve() -> int:
    from concurrent.futures import ThreadPoolExecutor

    engine = RapidOCR()
    workers = max(1, min(4, int(os.environ.get("OCR_SERVE_THREADS", "1") or 1)))
    pool = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
            files = [str(p) for p in request.get("files") or []]
        except Exception:
            sys.stdout.write(json.dumps({"ok": False, "blocks": [], "ms": []}) + "\n")
            sys.stdout.flush()
            continue
        started = time.time()
        blocks = _scan_files(engine, files, pool)
        timings = [int((time.time() - started) * 1000)]
        sys.stdout.write(
            json.dumps(
                {"ok": True, "blocks": blocks, "ms": timings}, ensure_ascii=False
            )
            + "\n"
        )
        sys.stdout.flush()
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        return serve()
    engine = RapidOCR()
    out = _scan_files(engine, sys.argv[1:])
    json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
