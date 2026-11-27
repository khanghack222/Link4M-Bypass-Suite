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
import sys
import time

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

MAX_WIDTH = 800


def read_lines(engine, path: str) -> list[str]:
    try:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        if w > MAX_WIDTH:
            im = im.resize((MAX_WIDTH, int(h * MAX_WIDTH / w)), Image.LANCZOS)
            tmp = path + ".small.png"
            im.save(tmp)
            path = tmp
        result, _ = engine(path)
        return [line[1] for line in (result or [])]
    except Exception:
        return []


def serve() -> int:
    from concurrent.futures import ThreadPoolExecutor

    engine = RapidOCR()
    workers = max(1, min(4, int(os.environ.get("OCR_SERVE_THREADS", "2") or 2)))
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
        if pool and len(files) > 1:
            blocks = list(pool.map(lambda path: read_lines(engine, path), files))
        else:
            blocks = [read_lines(engine, path) for path in files]
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
    out = [read_lines(engine, path) for path in sys.argv[1:]]
    json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
