#!/usr/bin/env python3
"""Solve Cloudflare Managed Challenge (`Just a moment...`) via Patchright and print cf_clearance JSON."""

import json
import os
import sys
import time
from patchright.sync_api import sync_playwright


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    url = sys.argv[1]
    proxy_url = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    ua = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    headless = os.environ.get("L4M_HEADLESS", "1") == "1"
    if headless:
        launch_args.append("--headless=new")

    kwargs = {
        "headless": headless,
        "args": launch_args,
    }
    chrome_bin = os.environ.get("CHROME_BIN", "").strip()
    if chrome_bin and os.path.exists(chrome_bin):
        kwargs["executable_path"] = chrome_bin
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}

    with sync_playwright() as p:
        browser = p.chromium.launch(**kwargs)
        try:
            ctx_kwargs = {}
            if ua:
                ctx_kwargs["user_agent"] = ua
            ctx = browser.new_context(**ctx_kwargs)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            for _ in range(15):
                title = page.title() or ""
                if "just a moment" not in title.lower():
                    for c in ctx.cookies():
                        if c.get("name") == "cf_clearance":
                            print(json.dumps({"ok": True, "cookie": c}))
                            return 0
                for frame in page.frames:
                    if "challenges.cloudflare.com" in (frame.url or ""):
                        try:
                            box = frame.frame_element().bounding_box()
                            if box:
                                page.mouse.click(
                                    box["x"] + 28, box["y"] + box["height"] / 2
                                )
                        except Exception:
                            pass
                time.sleep(1.5)
        finally:
            browser.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
