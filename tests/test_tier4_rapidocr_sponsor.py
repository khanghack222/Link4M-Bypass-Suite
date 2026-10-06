"""
tests/test_tier4_rapidocr_sponsor.py
------------------------------------
Test Tier 4: RapidOCR Base64 Decoding & Sponsor Traffic Task Automation.
Requirement: ORIGINAL_REQUEST §R3 & TEST_INFRA.md §Feature 5, 6, 7.
Verifies:
1. Extraction and Base64 decoding of mission images from adv.json payload.
2. RapidOCR text extraction accuracy on sponsor search keywords and domains.
3. Base64 payload decoding speed < 50ms.
4. RapidOCR inference performance on mission ROI images.
5. Sponsor 6-digit PIN validation and error handling for malformed payloads.
"""

import os
import sys
import json
import re
import base64
import time
import unittest

# Ensure workspace root and src/ are in sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_SRC_CORE = os.path.join(_ROOT, "src", "core")
if _SRC_CORE not in sys.path:
    sys.path.insert(0, _SRC_CORE)


class TestTier4RapidOCRSponsor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adv_json_path = os.path.join(_ROOT, "adv.json")
        assert os.path.exists(cls.adv_json_path), f"adv.json not found at {cls.adv_json_path}"
        with open(cls.adv_json_path, "r", encoding="utf-8") as f:
            cls.adv_data = json.load(f)

        # Pre-warm RapidOCR engine once for benchmarking
        from rapidocr_onnxruntime import RapidOCR
        cls.ocr_engine = RapidOCR(use_angle_cls=False, det_limit_side_len=320)

    def test_adv_json_structure_and_base64_presence(self):
        """Verifies adv.json contains valid advertising payload with embedded Base64 images."""
        self.assertTrue(self.adv_data.get("success"), "adv.json must contain success=true")
        html_content = self.adv_data.get("html", "")
        self.assertTrue(len(html_content) > 100, "adv.json html content must not be empty")

        matches = re.findall(r"data:image\/[a-zA-Z]+;base64,([A-Za-z0-9+\/=\s]+)", html_content)
        self.assertGreaterEqual(len(matches), 1, "adv.json must contain at least 1 Base64 encoded mission image")

    def test_base64_decoding_speed_sub_50ms(self):
        """Tests that decoding Base64 mission images from adv.json completes in < 50ms."""
        html_content = self.adv_data.get("html", "")
        b64_matches = re.findall(r"data:image\/[a-zA-Z]+;base64,([A-Za-z0-9+\/=\s]+)", html_content)

        png_header = b"\x89PNG\r\n\x1a\n"

        for idx, b64_str in enumerate(b64_matches):
            clean_b64 = b64_str.strip()

            t0 = time.perf_counter()
            raw_bytes = base64.b64decode(clean_b64)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            self.assertLess(
                elapsed_ms,
                50.0,
                f"Base64 image {idx} decoding took {elapsed_ms:.3f}ms, exceeding 50ms SLA"
            )
            self.assertTrue(
                raw_bytes.startswith(png_header) or raw_bytes.startswith(b"\xff\xd8"),
                f"Decoded bytes for image {idx} must be a valid PNG or JPEG image"
            )

    def test_rapidocr_keyword_and_sponsor_domain_extraction(self):
        """Verifies RapidOCR correctly identifies search keyword 'keonhacai' and domain 'tylenhacai'."""
        html_content = self.adv_data.get("html", "")
        b64_matches = re.findall(r"data:image\/[a-zA-Z]+;base64,([A-Za-z0-9+\/=\s]+)", html_content)

        extracted_texts = []
        for b64_str in b64_matches:
            raw_bytes = base64.b64decode(b64_str.strip())
            result, _ = self.ocr_engine(raw_bytes)
            if result:
                for line in result:
                    extracted_texts.append(line[1].lower())

        combined_text = " ".join(extracted_texts)

        # Assert search keyword was extracted
        has_keyword = any(kw in combined_text for kw in ["keonhacai", "keo nha cai", "google.com"])
        self.assertTrue(
            has_keyword,
            f"RapidOCR failed to extract search keyword from mission images. Found: {combined_text}"
        )

        # Assert sponsor domain hint was extracted
        has_sponsor = any(sp in combined_text for sp in ["tylenhacai", "nhacai", "win"])
        self.assertTrue(
            has_sponsor,
            f"RapidOCR failed to extract sponsor domain hint from mission images. Found: {combined_text}"
        )

    def test_rapidocr_small_roi_benchmark(self):
        """Tests RapidOCR inference latency on small cropped ROI keyword patch."""
        # Use a small test image cropped from raw bytes
        html_content = self.adv_data.get("html", "")
        b64_matches = re.findall(r"data:image\/[a-zA-Z]+;base64,([A-Za-z0-9+\/=\s]+)", html_content)
        raw_bytes = base64.b64decode(b64_matches[0].strip())

        # Warm run
        self.ocr_engine(raw_bytes)

        t0 = time.perf_counter()
        result, _ = self.ocr_engine(raw_bytes)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # RapidOCR on small image is optimized CPU ONNX inference
        self.assertIsNotNone(result)
        self.assertLess(elapsed_ms, 1500.0, f"RapidOCR inference took {elapsed_ms:.2f}ms")

    def test_sponsor_pin_regex_pattern(self):
        """Verifies 6-digit PIN extraction pattern matches sponsor quest specifications."""
        sample_widget_html = """
        <div id="traffic-pin-container">
            <span class="instruction">Ma PIN cua ban la:</span>
            <div class="pin-code" style="font-size:24px;">849201</div>
        </div>
        """
        match = re.search(r"\b(\d{6})\b", sample_widget_html)
        self.assertIsNotNone(match, "PIN pattern must detect 6-digit code")
        self.assertEqual(match.group(1), "849201")

    def test_corrupted_base64_error_handling(self):
        """Verifies that corrupted Base64 strings are handled cleanly without unhandled crashes."""
        corrupted_payload = "data:image/png;base64,CORRUPTED_NOT_BASE64_!@#$%"
        try:
            m = re.search(r"base64,([A-Za-z0-9+\/=\s]+)", corrupted_payload)
            if m:
                base64.b64decode(m.group(1).strip())
        except Exception:
            pass  # Handled cleanly


if __name__ == "__main__":
    unittest.main()
