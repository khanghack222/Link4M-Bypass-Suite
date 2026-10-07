#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for R3: Standalone Server-Side API & CLI Delivery
Validates src/cli.py and api_server.py POST /api/bypass endpoint.
"""

import sys
import os
import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock

# Configure paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
CORE_DIR = os.path.join(SRC_DIR, "core")

for p in [CORE_DIR, SRC_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
import api_server
from src.cli import parse_bool, resolve_bypass


class TestR3CliDelivery(unittest.TestCase):
    """Verifies CLI execution, argument parsing, JSON stdout output and exit codes."""

    def test_parse_bool_utility(self):
        self.assertTrue(parse_bool(True))
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("TRUE"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("yes"))
        self.assertFalse(parse_bool(False))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("no"))

    def test_cli_help(self):
        cmd = [sys.executable, "-m", "src.cli", "--help"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("--url", res.stdout)
        self.assertIn("--headless", res.stdout)
        self.assertIn("--timeout", res.stdout)
        self.assertIn("--proxy", res.stdout)

    def test_cli_missing_url(self):
        cmd = [sys.executable, "-m", "src.cli"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Missing required argument", data.get("error", ""))

    def test_cli_invalid_url_schema(self):
        cmd = [sys.executable, "-m", "src.cli", "--url", "ftp://example.com/file"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Invalid URL schema", data.get("error", ""))

    def test_cli_fast_base64_bypass(self):
        test_url = "https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9kb3dubG9hZF9maWxlLnppcA=="
        expected_dest = "https://example.com/download_file.zip"

        cmd = [sys.executable, "-m", "src.cli", "--url", test_url, "--headless"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"CLI stderr: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("destination_url"), expected_dest)
        self.assertEqual(data.get("url"), test_url)
        self.assertIsInstance(data.get("time_ms"), (int, float))
        self.assertGreater(data.get("time_ms"), 0)

    @patch("src.core.bypass.run")
    def test_cli_resolve_bypass_mocked_success(self, mock_bypass_run):
        mock_bypass_run.return_value = "https://final-destination.com/target"
        dest = resolve_bypass("https://link4m.net/go/test1234", headless=True, timeout=30, proxy=None)
        self.assertEqual(dest, "https://final-destination.com/target")
        mock_bypass_run.assert_called_once_with(
            target_url="https://link4m.net/go/test1234",
            headless=True,
            timeout=30,
            proxy=None
        )

    @patch("src.core.bypass.run")
    def test_cli_resolve_bypass_mocked_failure(self, mock_bypass_run):
        mock_bypass_run.return_value = None
        with patch("src.core.config.read_destination", return_value=""):
            with self.assertRaises(RuntimeError):
                resolve_bypass("https://link4m.net/go/fail1234", headless=True, timeout=30)


class TestR3ApiServer(unittest.TestCase):
    """Verifies FastAPI POST /api/bypass and /api/v1/bypass endpoints."""

    def setUp(self):
        self.client = TestClient(api_server.app)

    def test_api_missing_payload(self):
        resp = self.client.post("/api/bypass", json={})
        self.assertEqual(resp.status_code, 422)

    def test_api_invalid_url(self):
        resp = self.client.post("/api/bypass", json={"url": "not_a_valid_url"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid target URL", resp.json().get("detail", ""))

    def test_api_fast_base64_bypass(self):
        test_url = "https://bbmkts.com/go/file/aHR0cHM6Ly9nZHJpdmUubWUvZmlsZS8xMjM0NQ=="
        expected_dest = "https://gdrive.me/file/12345"

        resp = self.client.post("/api/bypass", json={"url": test_url, "headless": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("destination_url"), expected_dest)
        self.assertEqual(data.get("url"), test_url)
        self.assertIsInstance(data.get("time_ms"), (int, float))

    def test_api_v1_alias_endpoint(self):
        test_url = "https://bbmkts.com/go/file/aHR0cHM6Ly9tZWRpYWZpcmUuY29tL3ZpZXc="
        expected_dest = "https://mediafire.com/view"

        resp = self.client.post("/api/v1/bypass", json={"url": test_url})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("destination_url"), expected_dest)

    @patch("src.core.bypass.run")
    def test_api_core_bypass_success(self, mock_run):
        mock_run.return_value = "https://unlocked-destination.org/final"
        resp = self.client.post("/api/bypass", json={"url": "https://link4m.net/go/mocked", "headless": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("destination_url"), "https://unlocked-destination.org/final")
        self.assertIsInstance(data.get("time_ms"), (int, float))

    @patch("src.core.bypass.run")
    def test_api_core_bypass_failure(self, mock_run):
        mock_run.return_value = None
        with patch("src.core.config.read_destination", return_value=""):
            resp = self.client.post("/api/bypass", json={"url": "https://link4m.net/go/unresolvable", "headless": True})
            self.assertEqual(resp.status_code, 500)
            self.assertIn("could not unlock or extract final destination URL", resp.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
