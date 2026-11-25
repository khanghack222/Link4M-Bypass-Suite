#!/usr/bin/env python3
"""Chụp lưới reCAPTCHA đang hiện trên Chrome CDP và ghi index cho engine.

Engine (`link4m_engine.solve_grid`) chụp `#rc-imageselect-target` ra
`/tmp/grid_engine.png` rồi chờ index trong `/tmp/idx.txt`. Trên box headless
ảnh đó đôi khi không ghi được (locator timeout trong bframe), nên helper này
chụp lại bằng một CDP client riêng — CDP cho phép nhiều session cùng lúc, thao
tác chỉ đọc nên không đụng phiên của engine.

    python3 tools/grid_helper.py shot            # -> /tmp/grid_now.png + prompt
    python3 tools/grid_helper.py idx 1 4 7       # ghi /tmp/idx.txt
    python3 tools/grid_helper.py idx skip        # bỏ vòng lưới

`shot` in ra JSON: prompt, rows, cols, png, và text của lưới nếu có.
"""

import argparse
import base64
import json
import os
import sys

CDP = os.environ.get("CDP_URL", "http://127.0.0.1:9222")
GRID_IDX = "/tmp/idx.txt"
SHOT_PATH = "/tmp/grid_now.png"


def _connect():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(CDP, timeout=20000)
    return pw, browser


def _grid_frame(browser):
    """Chọn bframe có lưới thật: ưu tiên frame nằm trên màn hình và có tile.

    Trang có thể có nhiều widget reCAPTCHA; bframe của widget ẩn nằm ở
    `top:-9999px`, không có tile, và chụp ảnh từ đó sẽ treo.
    """
    ranked = []
    for context in browser.contexts:
        for page in context.pages:
            for frame in page.frames:
                try:
                    if not frame.locator("#rc-imageselect-target").count():
                        continue
                    tiles = frame.locator("div.rc-imageselect-tile").count()
                    box = frame.frame_element().bounding_box() or {}
                except Exception:
                    continue
                on_screen = box.get("width", 0) > 40 and box.get("y", -1) > -1000
                score = (2 if on_screen else 0) + (1 if tiles else 0)
                ranked.append((score, page, frame))
    if not ranked:
        return None, None
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, page, frame = ranked[0]
    return (page, frame) if score > 0 else (None, None)


def shot() -> int:
    pw, browser = _connect()
    try:
        page, frame = _grid_frame(browser)
        if frame is None:
            print(json.dumps({"error": "không thấy #rc-imageselect-target"}, ensure_ascii=False))
            return 1
        prompt = ""
        try:
            prompt = " ".join(frame.locator(
                ".rc-imageselect-desc-wrapper, .rc-imageselect-desc").first.inner_text().split())
        except Exception:
            pass
        rows = cols = 0
        try:
            geom = frame.evaluate("""() => {
              const t = document.querySelector('#rc-imageselect-target table');
              if (!t) return {rows: 0, cols: 0};
              const rows = t.querySelectorAll('tr').length;
              const cols = Math.max(...[...t.querySelectorAll('tr')].map(r => r.querySelectorAll('td').length));
              return {rows, cols};
            }""")
            rows, cols = int(geom.get("rows") or 0), int(geom.get("cols") or 0)
        except Exception:
            pass
        target = frame.locator("#rc-imageselect-target").first
        target.screenshot(path=SHOT_PATH, timeout=15000)
        size = os.path.getsize(SHOT_PATH) if os.path.exists(SHOT_PATH) else 0
        print(json.dumps({
            "prompt": prompt,
            "rows": rows,
            "cols": cols,
            "png": SHOT_PATH,
            "bytes": size,
            "page": page.url.split("?")[0],
        }, ensure_ascii=False))
        return 0 if size else 2
    finally:
        try:
            browser.close()
        except Exception:
            pass
        pw.stop()


def write_idx(tokens: list[str]) -> int:
    if not tokens:
        print("cần ít nhất một index hoặc 'skip'", file=sys.stderr)
        return 2
    if len(tokens) == 1 and tokens[0].lower() == "skip":
        payload = "skip\n"
    else:
        nums = []
        for token in tokens:
            token = token.strip()
            if not token.isdigit():
                print(f"index không phải số: {token}", file=sys.stderr)
                return 2
            nums.append(token)
        payload = " ".join(nums) + "\n"
    with open(GRID_IDX, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps({"idx": GRID_IDX, "content": payload.strip()}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shot", help="chụp lưới hiện tại")
    idx = sub.add_parser("idx", help="ghi index (1-based) cho engine")
    idx.add_argument("tokens", nargs="+")
    args = parser.parse_args()
    if args.cmd == "shot":
        return shot()
    if args.cmd == "idx":
        return write_idx(args.tokens)
    if args.cmd == "dump":
        # base64 để đọc ở nơi không mở được file
        pw, browser = _connect()
        try:
            _, frame = _grid_frame(browser)
            if frame is None:
                print("no grid", file=sys.stderr)
                return 1
            png = frame.locator("#rc-imageselect-target").first.screenshot(timeout=15000)
            print(base64.b64encode(png).decode())
            return 0
        finally:
            try:
                browser.close()
            except Exception:
                pass
            pw.stop()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
