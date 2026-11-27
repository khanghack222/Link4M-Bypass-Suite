#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Wave 13: fast_decode edge cases, self-reference guards, and provider_table host matrix.
Offline contract tests: no network, no browser, zero sleep delay.
"""

import base64
import os
import sys
import unittest
import urllib.parse

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "src", "core"))

from fast_decode import fast_decode
import provider_table as pt


class TestFastDecode(unittest.TestCase):
    """Test fast_decode base64 resolution, percent-encoding, query parameters, and self-reference protection."""

    def test_base64_go_file_standard_and_unpadded(self):
        target = "https://mediafire.com/file/xyz123"
        b64_std = base64.b64encode(target.encode("utf-8")).decode("utf-8")
        b64_unpadded = b64_std.rstrip("=")

        url1 = f"https://yeumoney.com/go/file/{b64_std}"
        url2 = f"https://bbmkts.com/go/file/{b64_unpadded}"

        self.assertEqual(fast_decode(url1), target)
        self.assertEqual(fast_decode(url2), target)

    def test_percent_encoded_and_double_percent_encoded(self):
        target = "https://mega.nz/file/abc#key"
        b64_target = base64.b64encode(target.encode("utf-8")).decode("utf-8")

        # Single percent-encoded
        encoded_once = urllib.parse.quote(b64_target, safe="")
        url_once = f"https://yeumoney.com/go/file/{encoded_once}"
        self.assertEqual(fast_decode(url_once), target)

        # Double percent-encoded
        encoded_twice = urllib.parse.quote(encoded_once, safe="")
        url_twice = f"https://yeumoney.com/go/file/{encoded_twice}"
        self.assertEqual(fast_decode(url_twice), target)

    def test_plain_url_in_go_file(self):
        target = "https://google.com/drive/folders/123"
        url = f"https://yeumoney.com/go/file/{urllib.parse.quote(target, safe='')}"
        self.assertEqual(fast_decode(url), target)

    def test_query_and_fragment_payload_extraction(self):
        target = "https://example.com/direct-download-target"
        b64_target = base64.b64encode(target.encode("utf-8")).decode("utf-8")

        # Query param url=
        url_query = f"https://short.io/step2?ref=123&url={b64_target}"
        self.assertEqual(fast_decode(url_query), target)

        # Fragment #payload
        url_fragment = f"https://short.io/go#{b64_target}"
        self.assertEqual(fast_decode(url_fragment), target)

    def test_self_reference_guard_prevents_recursive_shorteners(self):
        # A payload that decodes to a known shortener domain must be rejected
        shortener_targets = [
            "https://link4m.net/go/final_step",
            "https://sub.bbmkts.com/go/3p82s",
            "https://trafficvn.com/get/12345",
            "https://yeumoney.com/go/file/abc"
        ]
        for dest in shortener_targets:
            b64_dest = base64.b64encode(dest.encode("utf-8")).decode("utf-8")
            url = f"https://yeumoney.com/go/file/{b64_dest}"
            self.assertIsNone(
                fast_decode(url),
                f"fast_decode must reject self-referential shortener target: {dest}"
            )

    def test_invalid_or_non_url_payloads(self):
        self.assertIsNone(fast_decode(""))
        self.assertIsNone(fast_decode(None))
        self.assertIsNone(fast_decode("https://example.com/not-a-file-route"))

        # Payload that is not base64 or decodes to non-url text
        b64_non_url = base64.b64encode(b"just-plain-text-not-a-link").decode("utf-8")
        self.assertIsNone(fast_decode(f"https://yeumoney.com/go/file/{b64_non_url}"))


class TestProviderTableHostMatrix(unittest.TestCase):
    """Test provider_table host definitions, alias mapping, and engine specs."""

    def test_link4m_hosts_matrix(self):
        expected_hosts = [
            "link4m.net", "link4m.com", "link4m.co", "link4m.org",
            "link4m.vip", "link4m.pro", "link4m.me", "link4m.app"
        ]
        spec = pt.spec_for("LINK4M")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, "LINK4M")
        for h in expected_hosts:
            self.assertIn(h, spec.hosts, f"Host {h} must be in LINK4M_HOSTS")

    def test_bbmkts_and_yeumoney_hosts(self):
        spec = pt.spec_for("BBMKTS")
        self.assertIsNotNone(spec)
        self.assertIn("bbmkts.com", spec.hosts)
        self.assertIn("yeumoney.com", spec.hosts)

        # Aliases
        self.assertEqual(pt.canonical_key("BBMKT"), "BBMKTS")
        self.assertEqual(pt.canonical_key("yeumoney"), "BBMKTS")
        self.assertEqual(pt.canonical_key("YOUMONEY"), "BBMKTS")

    def test_gtraffic_hosts(self):
        spec = pt.spec_for("GTRAFFIC")
        self.assertIsNotNone(spec)
        self.assertIn("gtraffic.io", spec.hosts)
        self.assertIn("direct.gtraffic.io", spec.hosts)
        self.assertIn("client.gtraffic.io", spec.hosts)
        self.assertEqual(pt.canonical_key("DIRECT_GTRAFFIC"), "GTRAFFIC")

    def test_layma_hosts(self):
        spec = pt.spec_for("LAYMA")
        self.assertIsNotNone(spec)
        self.assertIn("layma.net", spec.hosts)
        self.assertEqual(pt.canonical_key("layma.net"), "LAYMA")

    def test_trafficvn_hosts(self):
        spec = pt.spec_for("TRAFFICVN")
        self.assertIsNotNone(spec)
        self.assertIn("trafficvn.com", spec.hosts)
        self.assertIn("trafficvn.net", spec.hosts)
        self.assertEqual(pt.canonical_key("traffic_vn"), "TRAFFICVN")
        self.assertEqual(pt.canonical_key("iatum"), "TRAFFICVN")

    def test_octolink_hosts_and_wildcards(self):
        spec = pt.spec_for("OCTOLINK")
        self.assertIsNotNone(spec)
        self.assertIn("octolink.vip", spec.hosts)
        self.assertIn("link999.app", spec.hosts)
        self.assertIn("link999.com", spec.hosts)
        self.assertIn("shortearn.net", spec.hosts)
        self.assertIn("uptolink.", spec.hosts)
        self.assertIn("linkhuongdan.", spec.hosts)
        self.assertEqual(spec.kind, pt.EngineKind.EXTERNAL_NODE)
        self.assertEqual(pt.canonical_key("link999"), "OCTOLINK")
        self.assertEqual(pt.canonical_key("uptolink"), "OCTOLINK")

    def test_decode_spec(self):
        spec = pt.spec_for("DECODE")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.kind, pt.EngineKind.DECODE)
        self.assertEqual(pt.canonical_key("base64"), "DECODE")
        self.assertEqual(pt.canonical_key("fastpath"), "DECODE")

    def test_unknown_key_handling(self):
        self.assertIsNone(pt.spec_for("unknown_provider"))
        self.assertIsNone(pt.spec_for(""))
        self.assertIsNone(pt.spec_for(None))
        self.assertIsNone(pt.canonical_key("unknown_provider"))


if __name__ == "__main__":
    unittest.main()
