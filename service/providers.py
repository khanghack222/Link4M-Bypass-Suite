# -*- coding: utf-8 -*-
"""Nhận diện nhà cung cấp shortlink + giải nhanh (fast-path) không cần browser.

Thêm nhà mới = thêm một mục trong ``PROVIDERS``. ``kind == "browser"`` thì đẩy
sang worker Chrome; ``kind == "decode"`` thì giải thẳng bằng biến đổi chuỗi.
"""
from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional

# host -> cấu hình. Giữ nhẹ, chỉ khai báo cái đang có engine thật.
PROVIDERS: dict[str, dict] = {
    "link4m": {
        "hosts": ("link4m.net", "link4m.com", "link4m.co", "link4m.vip", "link4m.pro"),
        "pattern": re.compile(r"/go/([A-Za-z0-9_-]+)"),
        "kind": "browser",
    },
    # Ví dụ để mở rộng sau (engine chưa có, khai báo sẵn khung):
    # "layma": {"hosts": ("layma.net",), "pattern": re.compile(r"/([A-Za-z0-9_-]+)$"), "kind": "browser"},
}

# regex giải nhanh: URL nằm trong path /go/file/<base64|encoded>
_GO_FILE = re.compile(r"/go/file/([A-Za-z0-9_\-%]+)")


@dataclass(frozen=True)
class Match:
    provider: str
    key: str
    url: str
    kind: str


def normalize(url: str) -> str:
    url = (url or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")
    return url


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def parse(url: str) -> Optional[Match]:
    """Nhận diện provider + key từ URL."""
    url = normalize(url)
    host = _host(url)
    if not host:
        return None
    for name, cfg in PROVIDERS.items():
        ok = any(host == h or host.endswith("." + h) for h in cfg["hosts"])
        if not ok:
            continue
        m = cfg["pattern"].search(urllib.parse.urlparse(url).path)
        if m:
            return Match(provider=name, key=m.group(1), url=url, kind=cfg["kind"])
    return None


def _try_b64(s: str) -> Optional[str]:
    try:
        dec = base64.b64decode(s + "===").decode("utf-8", errors="ignore")
        return dec if dec.startswith("http") else None
    except Exception:
        return None


def fast_decode(url: str) -> Optional[str]:
    """Giải các dạng không cần browser (BBMKTS /go/file/ và query base64)."""
    url = normalize(url)
    m = _GO_FILE.search(url)
    if m:
        part = urllib.parse.unquote(m.group(1))
        got = _try_b64(part) or _try_b64(urllib.parse.unquote(part))
        if got:
            return got
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    except Exception:
        return None
    for vals in q.values():
        for v in vals:
            if len(v) > 16:
                got = _try_b64(v)
                if got and not any(k in got.lower() for k in ("link4m", "bbmkts", "trafficvn")):
                    return got
    return None


def supported() -> list[str]:
    return sorted(PROVIDERS.keys())
