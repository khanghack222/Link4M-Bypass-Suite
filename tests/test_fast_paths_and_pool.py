#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ FAST PATHS, RUNNER CONTRACTS & WIN32 CLIPBOARD VERIFICATION ⚡
Offline deterministic tests validating upgraded components.
"""

import sys
import os
import time
import json

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")

sys.path.insert(0, CORE_DIR)
sys.path.insert(0, ROOT_DIR)

from base_runner import BaseBypassRunner, BypassResult
from errors import BypassError, DestinationNotFound
from runner_registry import get_runner, execute_engine
from runners import BBMKTSRunner, GTrafficRunner, Link4MRunner
from config import copy_to_clipboard, get_clipboard_text

def test_bbmkts_instant_preflight():
    runner = BBMKTSRunner()
    # Base64 encoded: https://example.com/target-file
    # "aHR0cHM6Ly9leGFtcGxlLmNvbS90YXJnZXQtZmlsZQ=="
    test_url = "https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS90YXJnZXQtZmlsZQ=="
    t0 = time.perf_counter()
    dest = runner.pre_flight(test_url)
    dt_ms = (time.perf_counter() - t0) * 1000

    assert dest == "https://example.com/target-file", f"Failed, got: {dest}"
    assert dt_ms < 50.0, f"Pre-flight too slow: {dt_ms}ms"
    print(f"[PASS] test_bbmkts_instant_preflight: {dest} in {dt_ms:.3f}ms")

def test_runner_registry_lookup():
    b_runner = get_runner("BBMKTS")
    assert isinstance(b_runner, BBMKTSRunner)

    g_runner = get_runner("GTRAFFIC")
    assert isinstance(g_runner, GTrafficRunner)

    l_runner = get_runner("LINK4M")
    assert isinstance(l_runner, Link4MRunner)
    print("[PASS] test_runner_registry_lookup: All runners correctly registered and mapped")

def test_win32_clipboard_roundtrip():
    if sys.platform != "win32":
        print("[SKIP] Win32 clipboard test on non-windows")
        return

    secret = f"https://test-link.com/verify-{time.time()}"
    t0 = time.perf_counter()
    copy_to_clipboard(secret)
    dt_copy_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    read_back = get_clipboard_text()
    dt_read_ms = (time.perf_counter() - t1) * 1000

    assert secret in read_back, f"Clipboard mismatch! Expected {secret}, got {read_back}"
    print(f"[PASS] test_win32_clipboard_roundtrip: write={dt_copy_ms:.3f}ms, read={dt_read_ms:.3f}ms")

def test_template_run_fastpath():
    runner = BBMKTSRunner()
    test_url = "https://yeumoney.com/go/file/aHR0cHM6Ly9nb29nbGUuY29tL3ZlcmlmeQ=="
    res = runner.run(test_url)
    assert res.success is True
    assert res.destination_url == "https://google.com/verify"
    assert res.engine == "BBMKTS"
    assert res.metadata.get("fast_path") is True
    print(f"[PASS] test_template_run_fastpath: {res.destination_url} in {res.duration_ms:.2f}ms")

if __name__ == "__main__":
    print("=== RUNNING FAST PATH & UPGRADE TESTS ===")
    test_bbmkts_instant_preflight()
    test_runner_registry_lookup()
    test_win32_clipboard_roundtrip()
    test_template_run_fastpath()
    print("=== ALL UPGRADE TESTS PASSED! ===")
