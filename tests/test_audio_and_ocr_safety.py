#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Wave 5: Python Concurrency Tempfile & DNS Timeout Hardening.
Verifies thread/worker isolated temp audio files, cleanup on error, and bounded DNS timeouts.
"""

import concurrent.futures
import os
import sys
import time
import unittest
from unittest.mock import patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, ".."))
_CORE_DIR = os.path.join(_ROOT_DIR, "src", "core")
for _p in (_CORE_DIR, _ROOT_DIR, os.path.join(_ROOT_DIR, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import captcha_audio
import ocr_helper


class TestAudioAndOcrSafety(unittest.TestCase):
    def test_temp_path_uniqueness_and_concurrency(self):
        """Verify _get_unique_temp_path creates distinct paths across concurrent threads."""
        def allocate_path():
            p = captcha_audio._get_unique_temp_path(".raw")
            self.assertTrue(os.path.exists(p))
            return p

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            paths = list(ex.map(lambda _: allocate_path(), range(16)))

        # Clean up created temp files
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

        self.assertEqual(len(paths), 16)
        self.assertEqual(len(set(paths)), 16, "All concurrent temp paths must be strictly unique")

    def test_raw16k_cleanup_on_sox_failure(self):
        """Verify _raw16k cleans up its temporary .raw file even when sox fails."""
        created_paths = []
        original_get_path = captcha_audio._get_unique_temp_path

        def tracking_get_path(suffix=""):
            p = original_get_path(suffix)
            created_paths.append(p)
            return p

        with patch.object(captcha_audio, "_get_unique_temp_path", side_effect=tracking_get_path):
            with patch("subprocess.run", side_effect=RuntimeError("sox execution failure")):
                with self.assertRaises(RuntimeError):
                    captcha_audio._raw16k("/dummy/input.mp3")

        self.assertEqual(len(created_paths), 1)
        self.assertFalse(
            os.path.exists(created_paths[0]),
            f"Temp raw file {created_paths[0]} was leaked after sox exception!"
        )

    def test_backwards_compatibility_and_exports(self):
        """Ensure all required functions and variables remain exported."""
        self.assertTrue(hasattr(captcha_audio, "AUDIO_FILE"))
        self.assertTrue(callable(captcha_audio.solve))
        self.assertTrue(callable(captcha_audio.transcribe_whisper))
        self.assertTrue(callable(captcha_audio.transcribe_vosk))
        self.assertTrue(callable(captcha_audio.transcribe_google))
        self.assertTrue(callable(captcha_audio.digits_of))
        self.assertEqual(captcha_audio.digits_of("four two eight"), "428")

    def test_ocr_dns_timeout_bounded(self):
        """Verify _dns_check bounds dead/hanging domain lookup without blocking."""
        def slow_resolver(domain):
            time.sleep(3.0)
            return "127.0.0.1"

        with patch("socket.gethostbyname", side_effect=slow_resolver):
            start = time.perf_counter()
            result = ocr_helper._dns_check("hanging-domain.example", timeout=0.25)
            elapsed = time.perf_counter() - start

        self.assertFalse(result, "_dns_check should return False when DNS hangs")
        self.assertLess(elapsed, 1.2, f"DNS check took {elapsed:.2f}s, expected <= 1.2s timeout")

    def test_has_traffic_widget_fast_fail_on_bad_domain(self):
        """Verify has_traffic_widget fast-fails when domain DNS fails."""
        with patch.object(ocr_helper, "_dns_check", return_value=False):
            self.assertFalse(ocr_helper.has_traffic_widget("nonexistent.invalid"))

    def test_has_traffic_widget_bounded_timeout_with_slow_dns(self):
        """Verify has_traffic_widget returns in < 2.2s when socket.gethostbyname hangs for 5.0s."""
        def hanging_resolver(domain):
            time.sleep(5.0)
            return "1.2.3.4"

        with patch("socket.gethostbyname", side_effect=hanging_resolver):
            start = time.perf_counter()
            result = ocr_helper.has_traffic_widget("hanging-domain.test")
            elapsed = time.perf_counter() - start

        self.assertFalse(result, "has_traffic_widget must return False on DNS timeout")
        self.assertLess(elapsed, 2.5, f"has_traffic_widget took {elapsed:.2f}s, expected <= 2.5s")

    def test_resolve_domain_caps_download_to_5mb(self):
        """Verify resolve_domain caps download buffer to at most 5MB."""
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = b""

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ocr_helper.resolve_domain("https://example.com/quest_step.png")
            mock_resp.read.assert_called_once_with(5 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
