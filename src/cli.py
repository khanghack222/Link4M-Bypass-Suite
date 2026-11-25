#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
⚡ LINK4M BYPASS SUITE - STANDALONE CLI DELIVERY ⚡
=============================================================================
Allows invoking:
    py -3.11 -m src.cli --url <link4m_url>
    python -m src.cli --url <link4m_url> [--headless] [--timeout SEC] [--proxy PROXY]

Returns clean, well-formatted JSON to stdout:
    {"destination_url": "...", "status": "success", "time_ms": ..., "url": ...}
=============================================================================
"""

import sys
import os
import io
import time
import json
import argparse
import urllib.parse
from typing import Optional, Dict, Any

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Configure module search paths
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SRC_DIR, ".."))
_CORE_DIR = os.path.join(_SRC_DIR, "core")

for _p in [_CORE_DIR, _SRC_DIR, _ROOT_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def parse_bool(val: Any) -> bool:
    """Parses various boolean representation formats."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "yes", "t", "y"):
            return True
        if v in ("false", "0", "no", "f", "n"):
            return False
    return bool(val)


def resolve_bypass(target_url: str, headless: bool = True, timeout: int = 60,
                   proxy: Optional[str] = None, engine: Optional[str] = None) -> str:
    """
    Resolve a shortlink to its destination through the unified registry.

    The zero-browser decode is imported from ``fast_decode`` (no Playwright), so
    the CLI's internal ``time_ms`` budget stays honest. Link4M keeps its proven
    legacy engine call shape when ``L4M_ENGINE`` is not ``cdp``.
    """
    u = target_url.strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        raise ValueError(f"Invalid URL schema: '{target_url}' (must start with http:// or https://)")

    # 1. Zero-browser fast path (cheap import, no Playwright)
    from fast_decode import fast_decode
    fast = fast_decode(u)
    if fast:
        return fast

    import runner_registry

    key = runner_registry.normalize_key(engine) if engine else runner_registry.classify(u)
    if not key or key == "GENERIC":
        raise RuntimeError(f"Unrecognised provider for: {u[:120]}")

    # 2. Link4M legacy engine: direct call keeps timeout/proxy semantics.
    if key == "LINK4M" and os.environ.get("L4M_ENGINE", "").strip().lower() != "cdp":
        from src.core import bypass
        result = bypass.run(target_url=u, headless=headless, timeout=timeout, proxy=proxy)
        if result and isinstance(result, str) and result.startswith("http"):
            return result
        fallback = _dest_file_fallback()
        if fallback:
            return fallback
        raise RuntimeError("Failed to resolve destination URL: engine completed without unlocking destination")

    # 3. Every other provider: one dispatch entry point.
    result = runner_registry.execute(u, engine=engine, headless=headless, proxy=proxy)
    if result.success and result.destination_url and result.destination_url.startswith("http"):
        return result.destination_url

    fallback = _dest_file_fallback()
    if fallback:
        return fallback
    raise RuntimeError(result.error_message or result.error_code
                       or "Failed to resolve destination URL: engine completed without unlocking destination")


def _dest_file_fallback() -> str:
    """Canonical last-resort read; honours BYPASS_RUN_ID and is test-patchable."""
    from src.core.config import read_destination
    try:
        fallback = (read_destination() or "").strip()
    except Exception:
        return ""
    if fallback and fallback.startswith("http") and not any(
            k in fallback.lower() for k in ["link4m", "bbmkts"]):
        return fallback
    return ""


class StderrRedirector:
    """Redirects stdout prints to stderr during engine execution to ensure pure JSON stdout."""
    def __enter__(self):
        self._orig_stdout = sys.stdout
        sys.stdout = sys.stderr
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._orig_stdout


def main():
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Link4M Bypass Suite - Standalone Server-Side CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=True
    )
    parser.add_argument(
        "--url", "-u",
        dest="url",
        type=str,
        default=None,
        help="Target Link4M shortlink URL to resolve (required)"
    )
    parser.add_argument(
        "positional_url",
        nargs="?",
        default=None,
        help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--headless", "-hl",
        dest="headless",
        nargs="?",
        const=True,
        default=True,
        type=parse_bool,
        help="Run browser engine in headless mode (default: True)"
    )
    parser.add_argument(
        "--head", "-w",
        dest="head",
        action="store_true",
        help="Run browser engine in windowed mode (overrides --headless)"
    )
    parser.add_argument(
        "--timeout", "-t",
        dest="timeout",
        type=int,
        default=60,
        help="Bypass execution timeout in seconds"
    )
    parser.add_argument(
        "--proxy", "-p",
        dest="proxy",
        type=str,
        default=None,
        help="Optional proxy (honoured only by the Link4M legacy engine)"
    )
    parser.add_argument(
        "--engine", "-e",
        dest="engine",
        type=str,
        default=None,
        help="Force an engine key (LINK4M, BBMKTS, GTRAFFIC, LAYMA, TRAFFICVN, OCTOLINK)"
    )
    parser.add_argument(
        "--list",
        dest="list_providers",
        action="store_true",
        help="Print supported providers as JSON and exit"
    )

    args = parser.parse_args()

    if args.list_providers:
        import runner_registry
        from provider_table import PROVIDER_TABLE
        payload = {
            "supported": runner_registry.supported(),
            "engines": {spec.key: spec.module for spec in PROVIDER_TABLE},
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        sys.exit(0)

    target_url = args.url or args.positional_url
    if not target_url:
        error_payload = {
            "status": "error",
            "error": "Missing required argument: --url <link4m_url>",
            "destination_url": None,
            "url": None,
            "time_ms": 0.0
        }
        sys.stdout.write(json.dumps(error_payload, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        sys.exit(2)

    headless = False if args.head else bool(args.headless)
    timeout = max(5, int(args.timeout)) if args.timeout else 60
    proxy = args.proxy.strip() if args.proxy else None

    t_start = time.perf_counter()
    try:
        # Redirect inner logs to stderr so stdout remains 100% valid JSON
        with StderrRedirector():
            dest_url = resolve_bypass(
                target_url=target_url,
                headless=headless,
                timeout=timeout,
                proxy=proxy,
                engine=args.engine
            )

        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        success_payload = {
            "status": "success",
            "destination_url": dest_url,
            "url": target_url,
            "time_ms": elapsed_ms
        }
        sys.stdout.write(json.dumps(success_payload, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        sys.exit(0)

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        err_msg = str(exc).strip() or exc.__class__.__name__
        error_payload = {
            "status": "error",
            "error": err_msg,
            "destination_url": None,
            "url": target_url,
            "time_ms": elapsed_ms
        }
        sys.stdout.write(json.dumps(error_payload, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
