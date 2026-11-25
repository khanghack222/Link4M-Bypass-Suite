#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ PROCESS-LEVEL BYPASS FAÇADE FOR JS FACES ⚡

    python -m src.bypass_api --url <url> [--engine KEY] [--headless] [--json]
    python -m src.bypass_api --list

This is the only command ``src/ui/menu.js``, ``bot_discord.js`` and
``service/worker.py`` shell out to. Engine log lines pass through untouched so
``formatLogLine()`` keeps matching them; this module adds the result card and
one canonical ``FINAL DESTINATION URL:`` line, plus an optional
``__BYPASS_JSON__{...}`` line for machine consumers.
"""

import argparse
import json
import os
import sys
from typing import Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SRC_DIR, ".."))
_CORE_DIR = os.path.join(_SRC_DIR, "core")
for _p in (_CORE_DIR, _SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import runner_registry  # noqa: E402
from provider_table import PROVIDER_TABLE  # noqa: E402
from base_runner import BypassResult  # noqa: E402

DEFAULT_TIMEOUT = 480


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m src.bypass_api",
        description="Link4M Bypass Suite — unified provider dispatch",
    )
    ap.add_argument("url", nargs="?", default=None, help="target shortlink URL")
    ap.add_argument("--url", "-u", dest="url_opt", default=None, help="target shortlink URL")
    ap.add_argument("--engine", "-e", default=None, help="force engine key (see --list)")
    ap.add_argument("--headless", "-hl", action="store_true", default=True,
                    help="headless browser (default)")
    ap.add_argument("--head", "-w", action="store_true", help="visible browser window")
    ap.add_argument("--json", action="store_true", help="emit __BYPASS_JSON__ line")
    ap.add_argument("--list", action="store_true", help="print supported providers as JSON")
    ap.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT,
                    help=f"engine budget in seconds (default {DEFAULT_TIMEOUT})")
    return ap


def list_payload() -> dict:
    return {
        "supported": runner_registry.supported(),
        "engines": {spec.key: spec.module for spec in PROVIDER_TABLE},
        "providers": [
            {
                "key": spec.key,
                "kind": spec.kind.value,
                "hosts": list(spec.hosts),
                "module": spec.module,
                "note": spec.note,
                "ready": spec.ready,
            }
            for spec in PROVIDER_TABLE
        ],
    }


def run_once(url: str, engine: Optional[str] = None, headless: bool = True,
             timeout: int = DEFAULT_TIMEOUT) -> BypassResult:
    resolved = runner_registry.normalize_key(engine) if engine else runner_registry.classify(url)
    use_cdp = (resolved == "LINK4M"
               and os.environ.get("L4M_ENGINE", "").strip().lower() == "cdp")
    if use_cdp:
        try:
            from link4m_engine import ensure_chrome  # noqa: WPS433
            ensure_chrome()
        except Exception as exc:
            return BypassResult(
                success=False,
                engine="LINK4M",
                provider="LINK4M",
                error_code="ERR_BROWSER_CRASH",
                error_message=f"Chrome CDP không sẵn sàng: {exc}",
                metadata={"timeout": timeout, "headless": headless},
                stage="pre_flight",
            )
    res = runner_registry.execute(url, engine=engine, headless=headless)
    res.metadata.setdefault("timeout", timeout)
    return res


def emit_result(res: BypassResult, as_json: bool) -> int:
    if res.success and res.destination_url:
        try:
            from config import log_result_card  # noqa: WPS433
            log_result_card(res.destination_url, res.provider or res.engine)
        except Exception:
            pass
        print(f"FINAL DESTINATION URL: {res.destination_url}", flush=True)
        rc = 0
    else:
        print(f"[ERROR] {res.error_code or 'ERR_UNKNOWN'}: "
              f"{res.error_message or 'bypass failed'}", flush=True)
        rc = 1
    if as_json:
        print("__BYPASS_JSON__" + json.dumps(res.to_dict(), ensure_ascii=False), flush=True)
    return rc


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        print(json.dumps(list_payload(), ensure_ascii=False, indent=2))
        return 0

    target = args.url_opt or args.url
    if not target:
        print("[ERROR] ERR_PROVIDER_UNKNOWN: missing --url", flush=True)
        return 2

    headless = False if args.head else bool(args.headless)
    as_json = bool(args.json) or os.environ.get("BYPASS_API_JSON", "") == "1"
    res = run_once(target, engine=args.engine, headless=headless,
                   timeout=max(5, int(args.timeout or DEFAULT_TIMEOUT)))
    return emit_result(res, as_json)


if __name__ == "__main__":
    sys.exit(main())
