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


def resolve_bypass(target_url: str, headless: bool = True, timeout: int = 60, proxy: Optional[str] = None) -> str:
    """
    Executes the Link4M bypass pipeline.
    Runs fast zero-click decoders first, then the core autonomous bypass engine.
    """
    u = target_url.strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        raise ValueError(f"Invalid URL schema: '{target_url}' (must start with http:// or https://)")

    # 1. Fast path: BBMKTS /go/file/ base64 / URL decode
    if "/go/file/" in u:
        encoded_part = u.split("/go/file/")[-1].split("?")[0].split("#")[0]
        import base64
        for dec_fn in [
            lambda s: base64.b64decode(s + "===").decode("utf-8", errors="ignore"),
            lambda s: urllib.parse.unquote(s)
        ]:
            try:
                dec = dec_fn(encoded_part)
                if dec.startswith("http"):
                    return dec
            except Exception:
                pass

    # 2. Fast path: Direct base64-encoded query parameters or hashes
    try:
        parsed = urllib.parse.urlparse(u)
        qparams = urllib.parse.parse_qs(parsed.query)
        for val_list in qparams.values():
            for v in val_list:
                if len(v) > 16:
                    import base64
                    try:
                        dec = base64.b64decode(v + "===").decode("utf-8", errors="ignore")
                        if dec.startswith("http") and not any(k in dec.lower() for k in ["link4m", "bbmkts", "trafficvn"]):
                            return dec
                    except Exception:
                        pass
    except Exception:
        pass

    # 3. Core Autonomous Bypass Engine
    from src.core import bypass
    result = bypass.run(target_url=u, headless=headless, timeout=timeout, proxy=proxy)

    if result and isinstance(result, str) and result.startswith("http"):
        return result

    # Check fallback destination file
    from src.core.config import read_destination
    fallback = read_destination()
    if fallback and fallback.startswith("http"):
        return fallback

    raise RuntimeError("Failed to resolve destination URL: engine completed without unlocking destination")


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
        help="Optional proxy server (e.g. http://user:pass@host:port or socks5://host:port)"
    )

    args = parser.parse_args()

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
                proxy=proxy
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
