#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ OFFLINE CORE UNIT TESTS FOR LINK4M BYPASS SUITE ⚡
Zero-network, deterministic unit tests verifying parser logic,
domain unmasking, math captcha heuristics, url classification, and session storage.
"""

import sys
import os
import re

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")

sys.path.insert(0, CORE_DIR)
sys.path.insert(0, ROOT_DIR)

from auto_bypass import classify_url
from config import save_destination, read_destination
from bbmkts_runner import clean_destination_url
from sponsor import unmask_domain_candidates, VN_MATH_NUMS

def test_classify_url():
    cases = [
        ("https://gtraffic.io/task/123", "GTRAFFIC"),
        ("https://direct.gtraffic.io/dr-client/X9", "GTRAFFIC"),
        ("https://bbmkts.com/go/abc", "BBMKTS"),
        ("https://yeumoney.com/go/file/abc", "BBMKTS"),
        ("https://layma.net/pohWNZgba", "LAYMA"),
        ("https://trafficvn.net/get/MFGm", "TRAFFICVN"),
        ("https://octolink.vip/abc", "OCTOLINK"),
        ("https://link4m.co/xyz", "LINK4M"),
        ("https://link4m.net/go/68pw167Y", "LINK4M"),
        ("https://unknownlink.com/123", "GENERIC")
    ]
    for url, expected in cases:
        actual = classify_url(url)
        assert actual == expected, f"Classification failed for {url}: expected {expected}, got {actual}"
    print("[PASS] test_classify_url")

def test_clean_destination_url():
    # Base64 with padding
    b64_url = "https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9maW5hbC1kb3dubG9hZA=="
    expected = "https://example.com/final-download"
    res = clean_destination_url(b64_url)
    assert res == expected, f"Expected {expected}, got {res}"

    # Plain url untouched
    plain = "https://google.com/test"
    assert clean_destination_url(plain) == plain
    print("[PASS] test_clean_destination_url")

def test_unmask_domain_candidates():
    samples = [
        ("shin-shih.co***.tw", ["shin-shih.com.tw", "shin-shih.co.tw", "shin-shih.tw"]),
        ("theyhouse.c***", ["theyhouse.com"]),
        ("myportal.n***", ["myportal.net"]),
        ("charity.o***", ["charity.org"]),
        ("vietnam.v***", ["vietnam.vn"])
    ]
    for raw, expected_candidates in samples:
        res = unmask_domain_candidates(raw)
        for exp in expected_candidates:
            assert exp in res, f"Expected {exp} in candidates {res} for raw {raw}"
    print("[PASS] test_unmask_domain_candidates")

def test_math_captcha_parser():
    def local_calc(v1_str, op, v2_str):
        def parse_v(s):
            s = s.strip().lower()
            if s.isdigit(): return int(s)
            return VN_MATH_NUMS.get(s)
        v1 = parse_v(v1_str)
        v2 = parse_v(v2_str)
        if v1 is None or v2 is None: return None
        if op == '+': return v1 + v2
        if op == '-': return v1 - v2
        if op == '*': return v1 * v2
        if op == '/': return v1 // v2 if v2 != 0 else 0
        return None

    assert local_calc("tam", "-", "nam") == 3
    assert local_calc("9", "+", "7") == 16
    assert local_calc("ba", "*", "hai") == 6
    assert local_calc("muoi", "/", "hai") == 5
    print("[PASS] test_math_captcha_parser")

def test_concurrency_destination_isolation():
    run_a = "test_run_a_unique"
    run_b = "test_run_b_unique"
    url_a = "https://dest.a/final"
    url_b = "https://dest.b/final"

    save_destination(url_a, run_id=run_a)
    save_destination(url_b, run_id=run_b)

    assert read_destination(run_id=run_a) == url_a, "Run A destination mismatch"
    assert read_destination(run_id=run_b) == url_b, "Run B destination mismatch"

    # Cleanup test files
    for r in [run_a, run_b]:
        p = os.path.join(ROOT_DIR, f"destination_url-{r}.txt")
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    print("[PASS] test_concurrency_destination_isolation")

def test_domain_utils_module():
    from domain_utils import unmask_domain_candidates as udc, VALID_TLDS
    assert len(VALID_TLDS) > 10, "VALID_TLDS should contain recognized TLDs"
    res = udc("brand.c***")
    assert "brand.com" in res, "Domain utils should expand brand.c*** to brand.com"
    print("[PASS] test_domain_utils_module")

def test_math_utils_module():
    from math_utils import VN_MATH_NUMS as vnm
    assert vnm["mot"] == 1 and vnm["sau"] == 6 and vnm["muoi"] == 10
    print("[PASS] test_math_utils_module")

if __name__ == "__main__":
    print("=== STARTING OFFLINE CORE UNIT TESTS ===")
    test_classify_url()
    test_clean_destination_url()
    test_unmask_domain_candidates()
    test_math_captcha_parser()
    test_domain_utils_module()
    test_math_utils_module()
    test_concurrency_destination_isolation()
    print("=== ALL OFFLINE UNIT TESTS PASSED (100%) ===")
