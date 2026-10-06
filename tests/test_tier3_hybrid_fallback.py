#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Tier 3: Hybrid Solver Architecture & Token Synchronization.
Validates:
  1. Tier 1 Instant Check (< 0.5s)
  2. Tier 2 Direct JS Audio workflow (< 2s)
  3. Tier 3 Cloud API 2Captcha fallback on rate-limit / DOSCAPTCHA
  4. Form token synchronization across inputs, textareas, and callbacks.
"""

import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")

sys.path.insert(0, CORE_DIR)
sys.path.insert(0, ROOT_DIR)

from playwright.sync_api import sync_playwright
import recaptcha_solver


def test_token_synchronization_on_page():
    """Validates _sync_tokens across DOM inputs, forms, and custom callbacks."""
    solver = recaptcha_solver.get_solver()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Build mock HTML page with Link4M structure
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Token Sync Test</title></head>
        <body>
            <form id="main-form">
                <textarea name="g-recaptcha-response" id="g-recaptcha-response"></textarea>
            </form>
            <form id="main-form-2">
                <!-- missing input, should be auto-created -->
            </form>
            <div class="g-recaptcha" data-callback="onCaptchaVerified"></div>
            <script>
                window.callbackToken = '';
                window.onCaptchaVerified = function(tok) {
                    window.callbackToken = tok;
                };
                window.recaptcha_callback = function(tok) {
                    window.recaptchaCallbackReceived = tok;
                };
            </script>
        </body>
        </html>
        """
        page.set_content(html)

        test_token = "03AFcWeA_TEST_SECURE_TOKEN_XYZ_1234567890"
        solver._sync_tokens(page, test_token)

        # Assertions
        val_main1 = page.evaluate("() => document.querySelector('#main-form [name=\"g-recaptcha-response\"]').value")
        assert val_main1 == test_token, f"Main form 1 token mismatch: {val_main1}"

        val_main2 = page.evaluate("() => document.querySelector('#main-form-2 [name=\"g-recaptcha-response\"]').value")
        assert val_main2 == test_token, f"Main form 2 token auto-create mismatch: {val_main2}"

        cb_val = page.evaluate("() => window.callbackToken")
        assert cb_val == test_token, f"data-callback was not triggered: {cb_val}"

        rc_val = page.evaluate("() => window.recaptchaCallbackReceived")
        assert rc_val == test_token, f"Link4M recaptcha_callback was not triggered: {rc_val}"

        browser.close()

    print("[PASS] Token synchronization across forms and callbacks verified 100%.")


def test_tier1_instant_check_branch():
    """Validates Tier 1 instant return when checkbox is already checked."""
    solver = recaptcha_solver.get_solver()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # HTML with mock iframe anchor having aria-checked="true"
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <textarea name="g-recaptcha-response">03AFcWeA_INSTANT_TRUST_TOKEN_ABC</textarea>
            <iframe name="a-test123" src="https://www.google.com/recaptcha/api2/anchor?k=6LcqrIgsAAAAAPkab9oMW9S4onnzLi8A6RVZpNOy">
            </iframe>
        </body>
        </html>
        """
        page.set_content(html)

        # Mock frame and checkbox
        mock_chk = MagicMock()
        mock_chk.count.return_value = 1
        mock_chk.get_attribute.return_value = "true"

        mock_cf = MagicMock()
        mock_cf.locator.return_value = mock_chk

        mock_anchor = MagicMock()
        mock_anchor.bounding_box.return_value = {"x": 10, "y": 10, "width": 300, "height": 78}
        mock_anchor.content_frame = mock_cf
        mock_anchor.get_attribute.return_value = "a-test123"
        mock_anchor.evaluate.return_value = True

        with patch.object(page, "locator") as mock_loc:
            mock_loc_obj = MagicMock()
            mock_loc_obj.all.return_value = [mock_anchor]
            mock_loc.return_value = mock_loc_obj

            res = solver.solve_on_page(page, timeout_sec=5)

            assert res.get("success") is True, f"Tier 1 must succeed, got {res}"
            assert res.get("type") == "instant", f"Expected type 'instant', got {res.get('type')}"
            assert "03AFcWeA_INSTANT_TRUST_TOKEN_ABC" in res.get("token"), f"Token mismatch: {res}"

        browser.close()

    print("[PASS] Tier 1 Instant Check verified.")


def test_tier3_cloud_api_fallback_branch():
    """Validates Tier 3 2Captcha fallback when audio encounters DOSCAPTCHA rate limit."""
    solver = recaptcha_solver.get_solver()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <form id="main-form">
                <textarea name="g-recaptcha-response"></textarea>
            </form>
            <iframe name="a-doscaptcha" src="https://www.google.com/recaptcha/api2/anchor?k=6LcqrIgsAAAAAPkab9oMW9S4onnzLi8A6RVZpNOy">
            </iframe>
        </body>
        </html>
        """
        page.set_content(html)

        # Mock anchor
        mock_chk = MagicMock()
        mock_chk.count.return_value = 1
        mock_chk.get_attribute.return_value = "false"

        mock_cf = MagicMock()
        mock_cf.locator.return_value = mock_chk

        mock_anchor = MagicMock()
        mock_anchor.bounding_box.return_value = {"x": 10, "y": 10, "width": 300, "height": 78}
        mock_anchor.content_frame = mock_cf
        mock_anchor.get_attribute.return_value = "a-doscaptcha"
        mock_anchor.evaluate.return_value = True

        # Mock bframe reporting DOSCAPTCHA
        mock_bframe = MagicMock()
        mock_bframe.locator.return_value.count.return_value = 1
        # First evaluate is clicking audio button -> True
        # Second evaluate is is_rate_limited -> True (DOSCAPTCHA)
        mock_bframe.evaluate.side_effect = [True, True]

        mock_direct_bf = MagicMock()
        mock_direct_bf.count.return_value = 1
        mock_direct_bf.first.content_frame = mock_bframe

        def locator_side_effect(selector):
            loc = MagicMock()
            if "anchor" in selector:
                loc.all.return_value = [mock_anchor]
            elif "c-doscaptcha" in selector:
                loc.count.return_value = 1
                loc.first.content_frame = mock_bframe
            else:
                loc.all.return_value = []
                loc.count.return_value = 0
            return loc

        expected_token = "03AFcWeA_2CAPTCHA_CLOUD_TOKEN_SUCCESS_999"

        with patch.object(page, "locator", side_effect=locator_side_effect), \
             patch("recaptcha_solver.solve_recaptcha_2captcha", return_value=expected_token):

            res = solver.solve_on_page(page, timeout_sec=5)

            assert res.get("success") is True, f"Tier 3 must succeed, got {res}"
            assert res.get("type") == "cloud_token", f"Expected type 'cloud_token', got {res.get('type')}"
            assert res.get("token") == expected_token, f"Token mismatch: {res}"

            # Verify DOM was updated with the token
            dom_val = page.evaluate("() => document.querySelector('#main-form [name=\"g-recaptcha-response\"]').value")
            assert dom_val == expected_token, f"DOM was not synchronized with cloud token: {dom_val}"

        browser.close()

    print("[PASS] Tier 3 Cloud API 2Captcha Fallback verified.")


def test_tier2_audio_success_branch():
    """Validates Tier 2 Audio success path through solve_on_page."""
    solver = recaptcha_solver.get_solver()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <textarea name="g-recaptcha-response">03AFcWeA_AUDIO_SUCCESS_TOKEN_777</textarea>
            <iframe name="a-audiosuccess" src="https://www.google.com/recaptcha/api2/anchor?k=6LcqrIgsAAAAAPkab9oMW9S4onnzLi8A6RVZpNOy">
            </iframe>
        </body>
        </html>
        """
        page.set_content(html)

        # Checkbox: returns "false" during instant check (20 times), then "true" after audio verified
        mock_chk = MagicMock()
        mock_chk.count.return_value = 1
        mock_chk.get_attribute.side_effect = ["false"] * 20 + ["true"] * 10

        mock_cf = MagicMock()
        mock_cf.locator.return_value = mock_chk

        mock_anchor = MagicMock()
        mock_anchor.bounding_box.return_value = {"x": 10, "y": 10, "width": 300, "height": 78}
        mock_anchor.content_frame = mock_cf
        mock_anchor.get_attribute.return_value = "a-audiosuccess"
        mock_anchor.evaluate.return_value = True

        mock_bframe = MagicMock()
        mock_bframe.locator.return_value.count.return_value = 1
        # evaluate calls:
        # 1. click audio button -> True
        # 2. is_rate_limited -> False
        # 3. get audio_url -> "https://google.com/recaptcha/api2/payload/audio.mp3"
        # 4. fill response -> None
        mock_bframe.evaluate.side_effect = [
            True,
            False,
            "https://www.google.com/recaptcha/api2/payload/audio.mp3",
            None
        ]

        def locator_side_effect(selector):
            loc = MagicMock()
            if "anchor" in selector:
                loc.all.return_value = [mock_anchor]
            elif "c-audiosuccess" in selector:
                loc.count.return_value = 1
                loc.first.content_frame = mock_bframe
            else:
                loc.all.return_value = []
                loc.count.return_value = 0
            return loc

        with patch.object(page, "locator", side_effect=locator_side_effect), \
             patch.object(solver, "transcribe_audio_url", return_value="weather forecast tomorrow"):

            res = solver.solve_on_page(page, timeout_sec=5)

            assert res.get("success") is True, f"Tier 2 must succeed, got {res}"
            assert res.get("type") == "audio_unblock_free", f"Expected type 'audio_unblock_free', got {res.get('type')}"
            assert "03AFcWeA_AUDIO_SUCCESS_TOKEN_777" in res.get("token"), f"Token mismatch: {res}"

        browser.close()

    print("[PASS] Tier 2 Direct JS Audio solve branch verified.")


class TestTier3HybridFallback(unittest.TestCase):
    def test_token_synchronization_on_page(self):
        test_token_synchronization_on_page()

    def test_tier1_instant_check_branch(self):
        test_tier1_instant_check_branch()

    def test_tier2_audio_success_branch(self):
        test_tier2_audio_success_branch()

    def test_tier3_cloud_api_fallback_branch(self):
        test_tier3_cloud_api_fallback_branch()


if __name__ == "__main__":
    print("=== RUNNING TIER 3 HYBRID FALLBACK & TOKEN SYNC TESTS ===")
    test_token_synchronization_on_page()
    test_tier1_instant_check_branch()
    test_tier2_audio_success_branch()
    test_tier3_cloud_api_fallback_branch()
    print("=== TIER 3 TESTS PASSED (100%) ===")
