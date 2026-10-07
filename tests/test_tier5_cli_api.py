#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_tier5_cli_api.py
----------------------------
Test Tier 5: Standalone CLI & REST API Delivery Verification.
Requirement: ORIGINAL_REQUEST §R3 & PROJECT.md §Feature Inventory (Standalone Delivery).

Validates:
1. R3 CLI interface:
   - `py -3.11 -m src.cli --help` exits with code 0 and prints full valid usage options.
   - Missing arguments exit with code 2 and structured error JSON.
   - Invalid URL schemas exit with code 1 and structured error JSON.
   - Real fast-path & mocked autonomous execution returns valid JSON with `destination_url` and `time_ms`.
   - Failure handling in bypass pipeline catches exceptions and outputs structured error JSON.

2. R3 REST API:
   - FastAPI endpoint `POST /api/bypass` registered and operational via TestClient.
   - Request schema validation (`{"url": "..."}`), missing fields return HTTP 422.
   - Invalid schema/types return HTTP 400 or 422.
   - Real fast-path & mocked autonomous execution return HTTP 200 with schema:
     `{"destination_url": "...", "time_ms": ..., "status": "success", ...}`.
   - Backend failure and exceptions return HTTP 500 with descriptive error details.
"""

import sys
import os
import io
import json
import time
import subprocess
import unittest
from unittest.mock import patch, MagicMock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
CORE_DIR = os.path.join(SRC_DIR, "core")

for p in [CORE_DIR, SRC_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import src.cli as cli
from api_server import app
from starlette.testclient import TestClient


class TestTier5Cli(unittest.TestCase):
    """Test suite for Standalone CLI delivery (`src.cli`)."""

    def test_cli_help_flag(self):
        """Asserts that `python -m src.cli --help` exits with code 0 and prints valid options."""
        cmd = [sys.executable, "-m", "src.cli", "--help"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        
        self.assertEqual(res.returncode, 0, f"CLI --help exited with non-zero: {res.stderr}")
        self.assertIn("--url", res.stdout, "CLI usage missing --url flag")
        self.assertIn("--headless", res.stdout, "CLI usage missing --headless flag")
        self.assertIn("--timeout", res.stdout, "CLI usage missing --timeout flag")
        self.assertIn("--proxy", res.stdout, "CLI usage missing --proxy flag")
        print("[PASS] CLI --help exits with code 0 and provides valid usage parameters.")

    def test_cli_missing_url_argument(self):
        """Asserts that invoking CLI without --url exits with code 2 and outputs valid error JSON."""
        cmd = [sys.executable, "-m", "src.cli"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        
        self.assertEqual(res.returncode, 2, "CLI without --url should exit with code 2")
        try:
            data = json.loads(res.stdout.strip())
        except Exception as e:
            self.fail(f"CLI stdout was not valid JSON: '{res.stdout}'. Error: {e}")
        
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Missing required argument", data.get("error", ""))
        self.assertIsNone(data.get("destination_url"))
        print("[PASS] CLI missing argument exits with code 2 and outputs structured error JSON.")

    def test_cli_invalid_url_schema(self):
        """Asserts that invoking CLI with invalid URL schema exits with code 1 and outputs error JSON."""
        cmd = [sys.executable, "-m", "src.cli", "--url", "ftp://invalid-domain.xyz"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        
        self.assertEqual(res.returncode, 1, "CLI with invalid URL should exit with code 1")
        try:
            data = json.loads(res.stdout.strip())
        except Exception as e:
            self.fail(f"CLI stdout was not valid JSON: '{res.stdout}'. Error: {e}")
        
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Invalid URL schema", data.get("error", ""))
        self.assertIsNone(data.get("destination_url"))
        print("[PASS] CLI invalid URL schema exits with code 1 and outputs structured error JSON.")

    def test_cli_fast_path_execution(self):
        """Asserts that BBMKTS /go/file/ base64 URL executes instantly and returns destination JSON."""
        # 'aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3dubG9hZA==' decodes to 'https://example.com/download'
        test_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3dubG9hZA=="
        cmd = [sys.executable, "-m", "src.cli", "--url", test_url]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        
        self.assertEqual(res.returncode, 0, f"Fast path CLI failed: {res.stderr}")
        try:
            data = json.loads(res.stdout.strip())
        except Exception as e:
            self.fail(f"CLI stdout was not valid JSON: '{res.stdout}'. Error: {e}")
        
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("destination_url"), "https://example.com/download")
        self.assertIsInstance(data.get("time_ms"), (int, float))
        self.assertGreaterEqual(data.get("time_ms"), 0.0)
        print(f"[PASS] CLI fast-path decoded URL in {data.get('time_ms')}ms returning valid JSON.")

    def test_cli_mocked_autonomous_success(self):
        """Asserts that mocked autonomous bypass run returns exit code 0 and valid JSON schema."""
        target_link = "https://link4m.net/go/68pw167Y"
        mock_destination = "https://truyenfull.vn/sample-story-chapter-1"

        with patch("src.cli.resolve_bypass", return_value=mock_destination), \
             patch("sys.argv", ["src.cli", "--url", target_link, "--headless"]):
            
            captured_stdout = io.StringIO()
            with patch("sys.stdout", captured_stdout):
                with self.assertRaises(SystemExit) as cm:
                    cli.main()
                self.assertEqual(cm.exception.code, 0)
            
            output_str = captured_stdout.getvalue().strip()
            data = json.loads(output_str)
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("destination_url"), mock_destination)
            self.assertEqual(data.get("url"), target_link)
            self.assertIsInstance(data.get("time_ms"), (int, float))
            print("[PASS] CLI mocked autonomous run succeeded with status=success and destination_url.")

    def test_cli_mocked_runtime_error(self):
        """Asserts that internal bypass failures exit with code 1 and structured error JSON."""
        target_link = "https://link4m.net/go/error-flow"

        with patch("src.cli.resolve_bypass", side_effect=RuntimeError("Google reCAPTCHA solve timeout")), \
             patch("sys.argv", ["src.cli", "--url", target_link]):
            
            captured_stdout = io.StringIO()
            with patch("sys.stdout", captured_stdout):
                with self.assertRaises(SystemExit) as cm:
                    cli.main()
                self.assertEqual(cm.exception.code, 1)
            
            output_str = captured_stdout.getvalue().strip()
            data = json.loads(output_str)
            self.assertEqual(data.get("status"), "error")
            self.assertIn("Google reCAPTCHA solve timeout", data.get("error"))
            self.assertIsNone(data.get("destination_url"))
            print("[PASS] CLI error handling catches internal exception and outputs clean error JSON.")


    def test_cli_positional_and_flag_precedence(self):
        """Asserts CLI handles positional URL and prioritizes --url flag when both present."""
        url_flag = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9mbGFn"
        url_pos = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9wb3M="
        cmd = [sys.executable, "-m", "src.cli", "--url", url_flag, url_pos]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data.get("destination_url"), "https://example.com/flag")
        print("[PASS] CLI handles positional argument and respects --url precedence.")

    def test_cli_stdout_purity_with_logger_redirection(self):
        """Asserts that logger or console output does NOT pollute stdout JSON."""
        test_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9wdXJpdHk="
        cmd = [sys.executable, "-m", "src.cli", "--url", test_url]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0)
        # Verify stdout is 100% valid JSON without leading/trailing non-whitespace artifacts
        raw_stdout = res.stdout.strip()
        self.assertTrue(raw_stdout.startswith("{") and raw_stdout.endswith("}"))
        parsed = json.loads(raw_stdout)
        self.assertEqual(parsed.get("status"), "success")
        print("[PASS] CLI stdout is 100% pure JSON without log pollution.")

    def test_cli_fast_path_latency_budget(self):
        """Asserts CLI fast-path execution time is within budget (<50ms internal resolution)."""
        test_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9sYXRlbmN5"
        cmd = [sys.executable, "-m", "src.cli", "--url", test_url]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertLess(data.get("time_ms", 100.0), 50.0, "CLI fast-path exceeded 50ms budget")
        print(f"[PASS] CLI fast-path latency budget verified: {data.get('time_ms')}ms < 50ms.")


class TestTier5RestApi(unittest.TestCase):
    """Test suite for Standalone REST API delivery (`POST /api/bypass`)."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_api_bypass_endpoint_registered(self):
        """Asserts that `/api/bypass` endpoint is registered on the FastAPI app."""
        route_paths = [r.path for r in app.routes]
        self.assertIn("/api/bypass", route_paths, "Route '/api/bypass' is not registered on FastAPI app.")
        print("[PASS] FastAPI endpoint '/api/bypass' is properly registered.")

    def test_api_bypass_missing_url_field(self):
        """Asserts that POST request with missing 'url' returns HTTP 422 Unprocessable Entity."""
        resp = self.client.post("/api/bypass", json={})
        self.assertEqual(resp.status_code, 422)
        errors = resp.json().get("detail", [])
        self.assertTrue(any("url" in str(err) for err in errors))
        print("[PASS] REST API validates required 'url' field and returns HTTP 422 on missing payload.")

    def test_api_bypass_invalid_url_type(self):
        """Asserts that POST request with non-string 'url' returns HTTP 422 Unprocessable Entity."""
        resp = self.client.post("/api/bypass", json={"url": 98765})
        self.assertEqual(resp.status_code, 422)
        print("[PASS] REST API validates 'url' type and returns HTTP 422 on integer payload.")

    def test_api_bypass_invalid_url_schema(self):
        """Asserts that POST request with invalid schema returns HTTP 400 Bad Request."""
        resp = self.client.post("/api/bypass", json={"url": "javascript:void(0)"})
        self.assertEqual(resp.status_code, 400)
        detail = resp.json().get("detail", "")
        self.assertIn("must start with http:// or https://", detail)
        print("[PASS] REST API rejects invalid URL protocol with HTTP 400 Bad Request.")

    def test_api_bypass_malformed_json_syntax(self):
        """Asserts that POST request with syntactically invalid JSON returns HTTP 422/400."""
        resp = self.client.post("/api/bypass", content="INVALID_JSON{{", headers={"Content-Type": "application/json"})
        self.assertIn(resp.status_code, (400, 422))
        print("[PASS] REST API handles malformed JSON syntax gracefully.")

    def test_api_bypass_whitespace_and_empty_url(self):
        """Asserts that POST request with empty or whitespace-only URL returns HTTP 400."""
        for bad_val in ["", "   \t\n"]:
            resp = self.client.post("/api/bypass", json={"url": bad_val})
            self.assertEqual(resp.status_code, 400)
        print("[PASS] REST API handles empty and whitespace URL inputs with HTTP 400.")

    def test_api_bypass_fast_path_latency_budget(self):
        """Asserts that REST API fast-path latency is well under 50ms."""
        test_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9sYXRlbmN5"
        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            resp = self.client.post("/api/bypass", json={"url": test_url})
            t1 = time.perf_counter()
            self.assertEqual(resp.status_code, 200)
            latencies.append((t1 - t0) * 1000)
        avg_lat = sum(latencies) / len(latencies)
        self.assertLess(avg_lat, 50.0, f"API fast path average latency {avg_lat:.2f}ms exceeded 50ms budget")
        print(f"[PASS] REST API fast-path average latency {avg_lat:.2f}ms < 50ms budget.")

    def test_api_bypass_fast_path_success(self):
        """Asserts that BBMKTS /go/file/ base64 URL returns HTTP 200 and schema compliant JSON."""
        # 'aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3dubG9hZA==' decodes to 'https://example.com/download'
        test_url = "https://link4m.net/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3dubG9hZA=="
        resp = self.client.post("/api/bypass", json={"url": test_url})
        
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("destination_url"), "https://example.com/download")
        self.assertIsInstance(data.get("time_ms"), (int, float))
        self.assertGreaterEqual(data.get("time_ms"), 0.0)
        print(f"[PASS] REST API fast-path bypass resolved in {data.get('time_ms')}ms returning HTTP 200.")

    def test_api_bypass_mocked_autonomous_success(self):
        """Asserts that mocked autonomous bypass returns HTTP 200 with destination_url and time_ms."""
        target_link = "https://link4m.net/go/68pw167Y"
        mock_dest = "https://final-unlocked-site.com/destination"

        with patch("src.core.bypass.run", return_value=mock_dest):
            resp = self.client.post("/api/bypass", json={"url": target_link, "headless": True, "timeout": 30})
            
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("destination_url"), mock_dest)
            self.assertEqual(data.get("url"), target_link)
            self.assertIsInstance(data.get("time_ms"), (int, float))
            print(f"[PASS] REST API mocked autonomous bypass resolved in {data.get('time_ms')}ms returning HTTP 200.")

    def test_api_bypass_backend_unlock_failure(self):
        """Asserts that backend failure to extract destination returns HTTP 500 with error detail."""
        target_link = "https://link4m.net/go/failed-link"

        with patch("src.core.bypass.run", return_value=None), \
              patch("src.core.config.read_destination", return_value=None):
            
            resp = self.client.post("/api/bypass", json={"url": target_link})
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            self.assertIn("could not unlock or extract final destination URL", data.get("detail", ""))
            print("[PASS] REST API handles backend unlock failure with HTTP 500 and clear error detail.")

    def test_api_bypass_backend_exception(self):
        """Asserts that backend unhandled exception is caught and returns HTTP 500."""
        target_link = "https://link4m.net/go/exception-link"

        with patch("src.core.bypass.run", side_effect=Exception("Playwright browser crash")):
            resp = self.client.post("/api/bypass", json={"url": target_link})
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            self.assertIn("Bypass execution error", data.get("detail", ""))
            print("[PASS] REST API handles backend execution exception with HTTP 500.")


if __name__ == "__main__":
    print("=== RUNNING TIER 5 CLI & REST API TEST SUITE ===")
    unittest.main(verbosity=2)
