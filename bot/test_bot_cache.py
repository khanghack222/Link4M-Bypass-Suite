#!/usr/bin/env python3
"""Unit tests for LinkCache and bot_discord_python response handling."""
import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from cache import LinkCache
from bot_discord_python import parse_bypass_response, LINK4M_REGEX


class TestLinkCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_cache.db")
        self.cache = LinkCache(db_path=self.db_path, default_ttl=3600)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            time.sleep(0.1)
            try:
                self.temp_dir.cleanup()
            except Exception:
                pass

    def test_cache_miss(self):
        self.assertIsNone(self.cache.get("nonexistent"))

    def test_cache_hit_and_hits_increment(self):
        alias = "2kCcIqn"
        dest = "https://example.com/target-destination"
        self.cache.set(alias, dest)

        # Initial check via get_entry
        entry = self.cache.get_entry(alias)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["alias"], alias)
        self.assertEqual(entry["destination_url"], dest)
        self.assertEqual(entry["hits"], 1)

        # First get increments hits to 2
        hit1 = self.cache.get(alias)
        self.assertEqual(hit1, dest)
        entry1 = self.cache.get_entry(alias)
        self.assertEqual(entry1["hits"], 2)

        # Second get increments hits to 3
        hit2 = self.cache.get(alias)
        self.assertEqual(hit2, dest)
        entry2 = self.cache.get_entry(alias)
        self.assertEqual(entry2["hits"], 3)

    def test_cache_expiry(self):
        alias = "expiring_link"
        dest = "https://example.com/expired"
        # Set with 1-second TTL
        self.cache.set(alias, dest, ttl=1)

        # Immediate check should hit
        self.assertEqual(self.cache.get(alias), dest)

        # Sleep past TTL
        time.sleep(1.1)

        # Now get should return None and entry should be pruned
        self.assertIsNone(self.cache.get(alias))
        self.assertIsNone(self.cache.get_entry(alias))

    def test_cache_overwrite(self):
        alias = "overwrite_me"
        self.cache.set(alias, "https://old.url")
        self.assertEqual(self.cache.get(alias), "https://old.url")

        self.cache.set(alias, "https://new.url")
        self.assertEqual(self.cache.get(alias), "https://new.url")

    def test_wal_mode_and_concurrency(self):
        """Verify database initializes in WAL mode and supports concurrent reads/writes."""
        import sqlite3
        import concurrent.futures
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        try:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")
        finally:
            conn.close()

        def worker(i):
            self.cache.set(f"concurrent_{i}", f"https://example.com/{i}")
            return self.cache.get(f"concurrent_{i}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(worker, range(20)))

        for i, res in enumerate(results):
            self.assertEqual(res, f"https://example.com/{i}")


class TestResponseParsing(unittest.TestCase):
    def test_engine_rs_success_status(self):
        payload = {
            "status": "success",
            "url": "https://link4m.net/go/2kCcIqn",
            "provider": "link4m",
            "destination_url": "https://mediafire.com/file/xyz",
            "elapsed_ms": 1250.0,
        }
        success, dest, err = parse_bypass_response(payload)
        self.assertTrue(success)
        self.assertEqual(dest, "https://mediafire.com/file/xyz")
        self.assertIsNone(err)

    def test_legacy_ok_status(self):
        payload = {
            "status": "ok",
            "destination": "https://drive.google.com/open?id=123",
        }
        success, dest, err = parse_bypass_response(payload)
        self.assertTrue(success)
        self.assertEqual(dest, "https://drive.google.com/open?id=123")
        self.assertIsNone(err)

    def test_engine_rs_failed_status(self):
        payload = {
            "status": "failed",
            "url": "https://link4m.net/go/2kCcIqn",
            "error": "captcha: Mã captcha đã sai hoặc quá hạn",
        }
        success, dest, err = parse_bypass_response(payload)
        self.assertFalse(success)
        self.assertIsNone(dest)
        self.assertIn("captcha", err)

    def test_engine_rs_timeout_status(self):
        payload = {
            "status": "timeout",
            "url": "https://link4m.net/go/2kCcIqn",
        }
        success, dest, err = parse_bypass_response(payload)
        self.assertFalse(success)
        self.assertIsNone(dest)
        self.assertIn("timeout", err)

    def test_invalid_payload(self):
        success, dest, err = parse_bypass_response(None)
        self.assertFalse(success)
        self.assertIsNone(dest)
        self.assertIn("Invalid", err)


class TestRegexValidation(unittest.TestCase):
    def test_link4m_regex_domains(self):
        valid_urls = [
            ("https://link4m.net/go/2kCcIqn", "2kCcIqn"),
            ("http://link4m.co/go/abc123_-", "abc123_-"),
            ("https://www.link4m.com/go/testLink", "testLink"),
            ("https://link4m.org/go/sample", "sample"),
            ("https://link4m.app/go/applink", "applink"),
            ("https://link4m.xyz/go/xyzlink", "xyzlink"),
        ]
        for url, expected_alias in valid_urls:
            m = LINK4M_REGEX.search(url)
            self.assertIsNotNone(m, f"Failed matching {url}")
            self.assertEqual(m.group(1), expected_alias)

    def test_invalid_urls(self):
        invalid_urls = [
            "https://google.com/search?q=link4m",
            "https://notlink4m.net/go/123",
            "ftp://link4m.net/go/123",
        ]
        for url in invalid_urls:
            m = LINK4M_REGEX.search(url)
            self.assertIsNone(m, f"Unexpected match for {url}")


if __name__ == "__main__":
    unittest.main()
