#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline contract tests for the unified provider registry.

No network, no browser, no Node. Run:  .venv/bin/python tests/test_provider_registry.py
"""

import json
import os
import sys
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "src", "core"))

import runner_registry as registry
from provider_table import canonical_key, spec_for


def test_detect_and_classify_matrix():
    cases = {
        # link4m family
        "https://link4m.net/go/2kCcIqn": "LINK4M",
        "https://link4m.co/go/abc": "LINK4M",
        "https://link4m.com/go/abc": "LINK4M",
        "https://www.link4m.org/go/abc": "LINK4M",
        # bbmkts / yeumoney
        "https://bbmkts.com/go/3p82s": "BBMKTS",
        "https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbQ==": "BBMKTS",
        # gtraffic
        "https://gtraffic.io/X3BR2OQ?ref=test": "GTRAFFIC",
        "https://direct.gtraffic.io/dr-client/ABC123": "GTRAFFIC",
        "https://client.gtraffic.io/X3BR2OQ": "GTRAFFIC",
        # layma
        "https://layma.net/pohWNZgba": "LAYMA",
        # trafficvn
        "https://trafficvn.net/get/MFGm2tAlcSn": "TRAFFICVN",
        "https://trafficvn.com/get/123": "TRAFFICVN",
        # octolink / link999 / uptolink / linkhuongdan
        "https://octolink.vip/abc": "OCTOLINK",
        "https://link999.app/x": "OCTOLINK",
        "https://link999.com/x": "OCTOLINK",
        "https://uptolink.biz/abc": "OCTOLINK",
        "https://www.uptolink.site/abc": "OCTOLINK",
        "https://linkhuongdan.net/abc": "OCTOLINK",
        "https://shortearn.net/abc": "OCTOLINK",
        # unknown
        "https://unknownlink.com/123": "GENERIC",
        "https://m.bahisbeta145.com/": "GENERIC",
        "not-a-url": "GENERIC",
        "": "GENERIC",
    }
    for url, expected in cases.items():
        got = registry.classify(url)
        assert got == expected, f"classify({url!r}): expected {expected}, got {got}"
        print(f"[PASS] classify {url or '<empty>'} -> {got}")


def test_alias_normalization():
    aliases = {
        "LINK999": "OCTOLINK",
        "uptolink": "OCTOLINK",
        "linkhuongdan": "OCTOLINK",
        "octo": "OCTOLINK",
        "shortearn": "OCTOLINK",
        "yeumoney": "BBMKTS",
        "bbmkt": "BBMKTS",
        "g-traffic": "GTRAFFIC",
        "layma.net": "LAYMA",
        "traffic_vn": "TRAFFICVN",
        "iatum": "TRAFFICVN",
        "l4m": "LINK4M",
        "link4": "LINK4M",
        "base64": "DECODE",
        "nonsense": None,
        "": None,
        None: None,
    }
    for raw, expected in aliases.items():
        got = canonical_key(raw) if raw is not None else canonical_key("")
        assert got == expected, f"canonical_key({raw!r}): expected {expected}, got {got}"
        print(f"[PASS] alias {raw!r} -> {got}")
    assert spec_for("link999") is spec_for("OCTOLINK")
    assert spec_for("LINK4M").hosts, "LINK4M hosts must not be empty"


def test_parse_key_slugs():
    cases = [
        ("https://link4m.net/go/2kCcIqn", ("LINK4M", "2kCcIqn")),
        ("https://bbmkts.com/go/3p82s?ref=x", ("BBMKTS", "3p82s")),
        ("https://trafficvn.com/get/MFGm2tAlcSn", ("TRAFFICVN", "MFGm2tAlcSn")),
        ("https://direct.gtraffic.io/X3BR2OQ", ("GTRAFFIC", "X3BR2OQ")),
        ("https://layma.net/pohWNZgba", ("LAYMA", "pohWNZgba")),
        ("https://octolink.vip/abc", ("OCTOLINK", "")),
    ]
    for url, expected in cases:
        got = registry.parse_key(url)
        assert got == expected, f"parse_key({url!r}): expected {expected}, got {got}"
        print(f"[PASS] parse_key {url} -> {got}")
    assert registry.parse_key("https://unknownlink.com/123") is None


def test_execute_unknown_provider():
    before = set(sys.modules)
    res = registry.execute("https://unknownlink.com/123")
    assert res.success is False
    assert res.error_code == "ERR_PROVIDER_UNKNOWN", res.error_code
    newly = set(sys.modules) - before
    for forbidden in ("runners", "bypass", "link4m_engine", "bbmkts_runner",
                      "gtraffic_runner", "layma_runner", "trafficvn_runner"):
        assert forbidden not in newly, f"engine module {forbidden} was imported for an unknown URL"
    print("[PASS] unknown provider fails fast without importing engines")


def test_execute_preflight_only():
    url = "https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS90YXJnZXQtZmlsZQ=="
    # Warm-up call pays the lazy runners import; the measured call must be pure string work.
    first = registry.execute(url)
    t0 = time.perf_counter()
    res = registry.execute(url)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert first.success and res.success
    assert res.destination_url == "https://example.com/target-file", res.destination_url
    assert res.metadata.get("fast_path") is True
    assert res.stage == "pre_flight", res.stage
    assert elapsed_ms < 50, f"pre-flight took {elapsed_ms:.1f}ms"
    print(f"[PASS] preflight-only resolve in {elapsed_ms:.2f}ms -> {res.destination_url}")


def test_execute_decode_provider():
    res = registry.execute("https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kZWNvZGVk")
    assert res.success and res.destination_url == "https://example.com/decoded"
    assert res.provider == "DECODE" and res.stage == "pre_flight"
    bad = registry.execute("https://example.com/no-payload")
    assert bad.success is False and bad.error_code == "ERR_PROVIDER_UNKNOWN"
    print("[PASS] DECODE provider fast path")


def test_supported_and_list_payload():
    keys = registry.supported()
    for expected in ("LINK4M", "BBMKTS", "GTRAFFIC", "LAYMA", "TRAFFICVN",
                     "OCTOLINK", "DECODE"):
        assert expected in keys, f"{expected} missing from supported()"
    from src import bypass_api
    payload = bypass_api.list_payload()
    text = json.dumps(payload, ensure_ascii=False)
    assert "LINK4M" in text and "OCTOLINK" in text
    assert all("key" in p and "hosts" in p for p in payload["providers"])
    print("[PASS] supported() + --list payload")


def test_alias_runner_lookup():
    from runners import OctoLinkRunner, Link4MRunner
    assert isinstance(registry.get_runner("link999"), OctoLinkRunner)
    assert isinstance(registry.get_runner("octo"), OctoLinkRunner)
    assert isinstance(registry.get_runner("L4M"), Link4MRunner)
    assert registry.get_runner("nonsense") is None
    print("[PASS] alias-aware get_runner()")


def test_fast_decode_rejects_self_reference():
    assert registry.fast_decode(
        "https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94") == "https://example.com/x"
    assert registry.fast_decode(
        "https://yeumoney.com/go/file/aHR0cHM6Ly9saW5rNG0ubmV0L2dvL2FiYw==") is None
    print("[PASS] fast_decode self-reference filter")


if __name__ == "__main__":
    print("=== RUNNING PROVIDER REGISTRY CONTRACT TESTS ===")
    test_detect_and_classify_matrix()
    test_alias_normalization()
    test_parse_key_slugs()
    test_execute_unknown_provider()
    test_execute_preflight_only()
    test_execute_decode_provider()
    test_supported_and_list_payload()
    test_alias_runner_lookup()
    test_fast_decode_rejects_self_reference()
    print("=== ALL PROVIDER REGISTRY TESTS PASSED ===")
