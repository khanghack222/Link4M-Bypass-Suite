# -*- coding: utf-8 -*-
"""Nhận diện nhà cung cấp shortlink + giải nhanh (fast-path) không cần browser.

Toàn bộ bảng provider nằm ở ``src/core/provider_table.py``; module này chỉ là
adapter mỏng cho FastAPI, giữ nguyên dataclass ``Match`` và payload API cũ.
"""
from __future__ import annotations

import os
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Optional

_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_DIR = os.path.abspath(os.path.join(_SERVICE_DIR, ".."))
_CORE_DIR = os.path.join(_REPO_DIR, "src", "core")
for _p in (_CORE_DIR, os.path.join(_REPO_DIR, "src"), _REPO_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import runner_registry  # noqa: E402
from provider_table import spec_for  # noqa: E402


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


def parse(url: str) -> Optional[Match]:
    """Nhận diện provider + key từ URL qua registry."""
    url = normalize(url)
    parsed = runner_registry.parse_key(url)
    if not parsed:
        return None
    key, slug = parsed
    spec = spec_for(key)
    if spec is None:
        return None
    return Match(provider=key.lower(), key=slug or url, url=url, kind=spec.kind.value)


def fast_decode(url: str) -> Optional[str]:
    return runner_registry.fast_decode(normalize(url))


def supported() -> list[str]:
    return sorted(k.lower() for k in runner_registry.supported() if k != "DECODE")
