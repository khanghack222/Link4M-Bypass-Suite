#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Client dòng lệnh cho service vượt link.

    python service/client.py https://link4m.net/go/2kCcIqn
    python service/client.py --base http://1.2.3.4:8080 --key SECRET --json <url>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8080"


def call(base: str, url: str, wait: bool, timeout: int, key: str | None) -> dict:
    qs = urllib.parse.urlencode({"url": url, "wait": "1" if wait else "0", "timeout": timeout})
    req = urllib.request.Request(f"{base.rstrip('/')}/api/v1/bypass?{qs}")
    if key:
        req.add_header("X-API-Key", key)
    with urllib.request.urlopen(req, timeout=timeout + 20) as r:
        return json.load(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Client vượt link")
    ap.add_argument("url", help="Link khoá")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--key", default=None, help="API key (nếu service bật)")
    ap.add_argument("--no-wait", action="store_true", help="Chỉ xếp hàng, trả job_id")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    t0 = time.time()
    try:
        res = call(a.base, a.url, not a.no_wait, a.timeout, a.key)
    except Exception as e:
        print(f"lỗi: {e}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("status") == "success" else 1

    dt = time.time() - t0
    if res.get("status") == "success":
        print(f"[ok] {res['destination_url']}")
        print(f"     {dt:.1f}s · {'cache' if res.get('cached') else 'mới'} · {res.get('provider')}")
        return 0
    print(f"[{res.get('status')}] {res.get('error') or res.get('detail') or ''}")
    if res.get("job_id"):
        print(f"     job {res['job_id']} -> {res.get('poll')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
