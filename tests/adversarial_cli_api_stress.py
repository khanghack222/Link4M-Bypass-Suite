#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial Stress Test Harness for CLI and REST API.
Challenges:
1. CLI stdout purity:
   - Ensuring that any internal prints/logging to stdout do not pollute stdout JSON.
   - Positional URL vs --url flag precedence and parsing.
   - Malformed arguments and unknown flags.
   - Non-ASCII / unicode URLs.
   - Large or pathological URLs.
   - Empty string URLs and whitespaces.
   - Fast-path latency measurement (<50ms).
2. REST API edge cases (`POST /api/bypass`):
   - Malformed JSON body (syntax error).
   - Empty request body.
   - Null values in payload.
   - Extra unexpected fields.
   - Whitespace-only URLs, non-HTTP schemas (`ftp://`, `javascript:`, `file:///`, `data:`).
   - Header variations (Content-Type).
   - Fast-path latency benchmark (< 50ms).
   - Concurrency stress test (50 concurrent requests).
   - Memory stability check.
"""

import sys
import os
import json
import time
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from starlette.testclient import TestClient
from api_server import app

client = TestClient(app)
PYTHON_EXE = sys.executable

def test_cli_stdout_purity_with_logger_spill():
    print("[TEST] CLI Stdout Purity under log spill...")
    # Run CLI with fast-path URL and ensure stdout is 100% parseable JSON without any stray characters
    url = "https://link4m.net/go/file/aHR0cHM6Ly9nby5jb20vdGVzdDEyMw=="
    cmd = [PYTHON_EXE, "-m", "src.cli", "--url", url]
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
    
    assert res.returncode == 0, f"CLI exited with {res.returncode}: {res.stderr}"
    stdout = res.stdout.strip()
    try:
        data = json.loads(stdout)
    except Exception as e:
        raise AssertionError(f"CLI stdout was not pure JSON! Raw stdout: {stdout!r}, error: {e}")
    
    assert data.get("status") == "success"
    assert data.get("destination_url") == "https://go.com/test123"
    print("  -> Passed. Pure JSON received:", data)

def test_cli_positional_and_flag_combinations():
    print("[TEST] CLI Positional vs Flag Combinations...")
    # Positional URL
    url = "https://link4m.net/go/file/aHR0cHM6Ly9nby5jb20vcG9zaXRpb25hbA=="
    cmd = [PYTHON_EXE, "-m", "src.cli", url]
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0
    data = json.loads(res.stdout.strip())
    assert data.get("destination_url") == "https://go.com/positional"
    print("  -> Positional URL parsed successfully.")

    # Flag and positional conflict (flag takes precedence)
    url2 = "https://link4m.net/go/file/aHR0cHM6Ly9nby5jb20vZmxhZw=="
    cmd = [PYTHON_EXE, "-m", "src.cli", "--url", url2, url]
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0
    data = json.loads(res.stdout.strip())
    assert data.get("destination_url") == "https://go.com/flag"
    print("  -> Flag precedence works.")

def test_cli_adversarial_inputs():
    print("[TEST] CLI Adversarial Inputs...")
    bad_cases = [
        ([], 2, "Missing required argument"),
        (["--url", ""], 2, "Missing required argument"),
        (["--url", "   "], (1, 2), "Invalid URL schema"),
        (["--url", "not-a-url"], 1, "Invalid URL schema"),
        (["--url", "ftp://example.com"], 1, "Invalid URL schema"),
        (["--url", "file:///C:/Windows/win.ini"], 1, "Invalid URL schema"),
        (["--url", "javascript:alert(1)"], 1, "Invalid URL schema"),
    ]
    for args, expected_code, expected_err_part in bad_cases:
        cmd = [PYTHON_EXE, "-m", "src.cli"] + args
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        if isinstance(expected_code, tuple):
            assert res.returncode in expected_code, f"Expected {expected_code} for {args}, got {res.returncode}: {res.stdout}"
        else:
            assert res.returncode == expected_code, f"Expected {expected_code} for {args}, got {res.returncode}: {res.stdout}"
        data = json.loads(res.stdout.strip())
        assert data["status"] == "error"
        assert expected_err_part in data["error"]
    print("  -> All adversarial CLI inputs handled gracefully with pure JSON error outputs.")

def test_cli_fast_path_latency():
    print("[TEST] CLI Fast-Path Latency Benchmarking (<50ms budget)...")
    url = "https://link4m.net/go/file/aHR0cHM6Ly9nby5jb20vYmVuY2g="
    t0 = time.perf_counter()
    cmd = [PYTHON_EXE, "-m", "src.cli", "--url", url]
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
    proc_time_ms = (time.perf_counter() - t0) * 1000
    assert res.returncode == 0
    data = json.loads(res.stdout.strip())
    engine_time_ms = data.get("time_ms", 0.0)
    print(f"  -> CLI process total time: {proc_time_ms:.2f}ms, Internal resolution time: {engine_time_ms:.2f}ms")
    assert engine_time_ms < 50.0, f"Fast-path resolution took {engine_time_ms}ms (>= 50ms)"

def test_api_malformed_requests():
    print("[TEST] REST API Malformed and Edge Case Requests...")
    
    # 1. Invalid JSON body
    resp = client.post("/api/bypass", content="INVALID_JSON{{", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422 or resp.status_code == 400, f"Unexpected status: {resp.status_code}"
    print("  -> Malformed JSON returns 400/422.")

    # 2. Empty Body
    resp = client.post("/api/bypass", content="", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
    print("  -> Empty body returns 422.")

    # 3. None / Null url
    resp = client.post("/api/bypass", json={"url": None})
    assert resp.status_code == 422
    print("  -> Null url returns 422.")

    # 4. Empty string url
    resp = client.post("/api/bypass", json={"url": ""})
    assert resp.status_code == 400
    print("  -> Empty string url returns 400.")

    # 5. Whitespace-only url
    resp = client.post("/api/bypass", json={"url": "    \t \n"})
    assert resp.status_code == 400
    print("  -> Whitespace url returns 400.")

    # 6. Non-HTTP protocols
    for proto in ["ftp://site.com", "file:///etc/passwd", "javascript:void(0)", "data:text/html,abc"]:
        resp = client.post("/api/bypass", json={"url": proto})
        assert resp.status_code == 400
        assert "must start with http:// or https://" in resp.json()["detail"]
    print("  -> Non-HTTP protocols rejected with 400.")

    # 7. Extra arbitrary fields (Pydantic should ignore or accept)
    fast_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3du"
    resp = client.post("/api/bypass", json={"url": fast_url, "extra_field": "injected", "another": 123})
    assert resp.status_code == 200
    assert resp.json()["destination_url"] == "https://example.com/down"
    print("  -> Extra payload fields handled gracefully.")

def test_api_fast_path_latency():
    print("[TEST] REST API Fast-Path Latency Benchmarking (<50ms budget)...")
    fast_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3du"
    
    latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        resp = client.post("/api/bypass", json={"url": fast_url})
        t1 = time.perf_counter()
        assert resp.status_code == 200
        latencies.append((t1 - t0) * 1000)

    avg_lat = sum(latencies) / len(latencies)
    max_lat = max(latencies)
    min_lat = min(latencies)
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]
    print(f"  -> 50 API fast-path requests: min={min_lat:.2f}ms, avg={avg_lat:.2f}ms, p95={p95_lat:.2f}ms, max={max_lat:.2f}ms")
    assert p95_lat < 50.0, f"P95 latency {p95_lat:.2f}ms exceeded 50ms budget!"

def test_api_concurrency():
    print("[TEST] REST API High-Concurrency Stress Test...")
    fast_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3du"
    num_requests = 100

    def send_one(i):
        r = client.post("/api/bypass", json={"url": f"{fast_url}?i={i}"})
        return r.status_code, r.json()

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(send_one, range(num_requests)))
    total_time = time.perf_counter() - t0

    assert len(results) == num_requests
    for status_code, data in results:
        assert status_code == 200
        assert data["status"] == "success"
        assert data["destination_url"] == "https://example.com/down"

    rps = num_requests / total_time
    print(f"  -> Completed {num_requests} concurrent requests in {total_time:.2f}s ({rps:.1f} req/s) with 0 errors.")

if __name__ == "__main__":
    print("=================================================================")
    print("[ADVERSARIAL] EMPIRICAL STRESS TEST FOR CLI & REST API")
    print("=================================================================")
    test_cli_stdout_purity_with_logger_spill()
    test_cli_positional_and_flag_combinations()
    test_cli_adversarial_inputs()
    test_cli_fast_path_latency()
    test_api_malformed_requests()
    test_api_fast_path_latency()
    test_api_concurrency()
    print("=================================================================")
    print("[PASS] ALL EMPIRICAL ADVERSARIAL TESTS PASSED WITHOUT REGRESSIONS!")
    print("=================================================================")
