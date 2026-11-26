#!/usr/bin/env python3
"""OCR sidecar for the campaign instruction images.

The instruction strip embeds the search keyword and the sponsor domain as
bitmap text, so the engine hands the decoded images to this helper and gets
plain lines back. RapidOCR runs on CPU with the bundled ONNX models; no
network access, no paid API.

Images are downscaled to 800 px before recognition: the source strips are
screenshots of large UI text, and the full-resolution pass costs ~3x more for
the same characters.
"""

import json
import sys

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

MAX_WIDTH = 800


def main() -> int:
    engine = RapidOCR()
    out = []
    for path in sys.argv[1:]:
        try:
            im = Image.open(path).convert("RGB")
            w, h = im.size
            if w > MAX_WIDTH:
                im = im.resize((MAX_WIDTH, int(h * MAX_WIDTH / w)), Image.LANCZOS)
                tmp = path + ".small.png"
                im.save(tmp)
                path = tmp
            result, _ = engine(path)
            out.append([line[1] for line in (result or [])])
        except Exception:
            out.append([])
    json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
