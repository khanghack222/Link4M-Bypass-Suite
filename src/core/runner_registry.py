#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ RUNNER REGISTRY — SINGLE DISPATCH ENTRY FOR EVERY FACE ⚡

One provider table, one classifier, one fast-path decoder, one execute().
Faces (auto_bypass, src/cli, src/bypass_api, service/worker) call this module;
none of them keeps its own host table any more.

Engine modules are imported lazily: ``bypass.py`` re-execs the interpreter at
import time, so a top-level import here would make ``--list`` restart the
process. Registry scope imports only stdlib plus the dependency-free
``base_runner``/``provider_table``/``fast_decode`` trio.
"""

import os
import sys
import time
import urllib.parse
from typing import Dict, Optional, Tuple, Type

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

# Same module object whether imported flat (`runner_registry`) or packaged
# (`src.core.runner_registry`), so runners.py registers into one table.
sys.modules.setdefault("runner_registry", sys.modules[__name__])

from base_runner import BaseBypassRunner, BypassResult  # noqa: E402
from provider_table import (  # noqa: E402
    GENERIC_KEY,
    PROVIDER_TABLE,
    EngineKind,
    ProviderSpec,
    canonical_key,
    spec_for,
)

_RUNNERS: Dict[str, Type[BaseBypassRunner]] = {}


def register_runner(engine_key: str):
    """Decorator to register a runner implementation."""
    def decorator(cls: Type[BaseBypassRunner]):
        key = canonical_key(engine_key)
        if key is None:
            print(f"[registry] unknown engine key ignored: {engine_key}", file=sys.stderr)
            key = engine_key.upper()
        _RUNNERS[key] = cls
        return cls
    return decorator


def _ensure_runners() -> bool:
    if _RUNNERS:
        return True
    try:
        import runners  # noqa: F401,WPS433 - self-registers all six engines
        return True
    except Exception as exc:  # browser deps missing on a bare box
        print(f"[registry] engine import failed: {exc}", file=sys.stderr)
        return False


def get_runner(engine_key: str) -> Optional[BaseBypassRunner]:
    """Alias-aware factory: ``get_runner("link999")`` -> OctoLinkRunner()."""
    key = normalize_key(engine_key) or (engine_key or "").strip().upper()
    cls = _RUNNERS.get(key)
    return cls() if cls else None


def execute_engine(engine_key: str, target_url: str, headless: bool = True) -> BypassResult:
    """Backwards-compatible entry point; delegates to ``execute()``."""
    return execute(target_url, engine=engine_key, headless=headless)


# ------------------------------------------------------------------ detection
def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if u and "://" not in u:
        u = "https://" + u.lstrip("/")
    return u


def _host(url: str) -> str:
    try:
        h = (urllib.parse.urlparse(_normalize_url(url)).hostname or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def _host_matches(host: str, pattern: str) -> bool:
    if not host or not pattern:
        return False
    if pattern.startswith("*."):
        base = pattern[2:]
        return host == base or host.endswith("." + base)
    if pattern.endswith("."):
        return host.startswith(pattern)
    return host == pattern or host.endswith("." + pattern)


def detect(url: str) -> Optional[ProviderSpec]:
    """Host match; None when the host is not a known provider.

    The path pattern is used to *extract* a slug, never to reject a host: the
    historical classifiers (auto_bypass, brain, menu.js) all matched on host,
    so ``link4m.co/xyz`` must still classify as LINK4M even without ``/go/``.
    """
    u = _normalize_url(url)
    host = _host(u)
    if not host:
        return None
    for spec in PROVIDER_TABLE:
        if spec.kind is EngineKind.DECODE:
            continue
        if any(_host_matches(host, h) for h in spec.hosts):
            return spec
    return None


def classify(url: str) -> str:
    spec = detect(url)
    return spec.key if spec else GENERIC_KEY


def normalize_key(raw: str) -> Optional[str]:
    return canonical_key(raw)


def supported() -> list:
    return sorted(spec.key for spec in PROVIDER_TABLE)


def parse_key(url: str) -> Optional[Tuple[str, str]]:
    """Return (canonical key, slug). Slug is ``""`` when the pattern has none."""
    spec = detect(url)
    if spec is None:
        return None
    slug = ""
    if spec.url_pattern is not None:
        try:
            path = urllib.parse.urlparse(_normalize_url(url)).path or ""
        except Exception:
            path = ""
        m = spec.url_pattern.search(path)
        if m and m.groups():
            slug = m.group(1) or ""
    return spec.key, slug


# ------------------------------------------------------------------ fast path
from fast_decode import fast_decode  # noqa: E402,F401 - re-exported API


# ------------------------------------------------------------------ dispatch
def _result_fail(url: str, key: Optional[str], code: str, message: str,
                  headless: bool, start: float) -> BypassResult:
    return BypassResult(
        success=False,
        engine=key or "UNKNOWN",
        provider=key,
        duration_ms=(time.perf_counter() - start) * 1000,
        error_code=code,
        error_message=message,
        metadata={"headless": headless, "url": url},
        stage="pre_flight",
    )


def execute(url: str, *, engine: Optional[str] = None, headless: bool = True,
            proxy: Optional[str] = None) -> BypassResult:
    start = time.perf_counter()
    raw = (url or "").strip()
    if not raw:
        return _result_fail(raw, None, "ERR_PROVIDER_UNKNOWN", "empty url", headless, start)

    key = normalize_key(engine) if engine else classify(raw)
    if not key or key == GENERIC_KEY:
        return _result_fail(raw, None, "ERR_PROVIDER_UNKNOWN",
                            f"unrecognised provider for: {raw[:120]}", headless, start)

    spec = spec_for(key)
    if spec is None:
        return _result_fail(raw, key, "ERR_PROVIDER_UNKNOWN",
                            f"unknown provider key: {key}", headless, start)

    if spec.kind is EngineKind.DECODE:
        fast = fast_decode(raw)
        if fast:
            return BypassResult(
                success=True,
                destination_url=fast.strip(),
                engine="DECODE",
                duration_ms=(time.perf_counter() - start) * 1000,
                metadata={"fast_path": True, "headless": headless},
                provider="DECODE",
                stage="pre_flight",
            )
        return _result_fail(raw, "DECODE", "ERR_DESTINATION_NOT_FOUND",
                            "no decodable payload in url", headless, start)

    _ensure_runners()
    runner = get_runner(spec.key)
    if runner is None or not spec.ready:
        return _result_fail(raw, spec.key, "ERR_RUNNER_NOT_FOUND",
                            f"No runner registered for engine: {spec.key}", headless, start)
    runner.proxy = proxy

    fast = fast_decode(raw)
    if fast and runner.is_valid_destination(fast):
        return BypassResult(
            success=True,
            destination_url=fast.strip(),
            engine="DECODE",
            duration_ms=(time.perf_counter() - start) * 1000,
            metadata={"fast_path": True, "headless": headless},
            provider="DECODE",
            stage="pre_flight",
        )

    res = runner.run(raw)
    res.provider = res.provider or spec.key
    res.stage = res.stage or ("pre_flight" if res.metadata.get("fast_path") else "browser")
    res.metadata.setdefault("headless", headless)
    res.metadata.setdefault("url", raw)
    return res
