#!/usr/bin/env python3
"""Unit tests for Discord Bot Python Client contract, payload validation, and error resilience."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Add repository root and bot/ to import path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BOT_DIR = os.path.join(REPO_ROOT, "bot")
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bot_discord_python as bot_mod


class FakeAsyncContextManager:
    """Helper to mock async with expressions."""
    def __init__(self, target=None, exc=None):
        self.target = target
        self.exc = exc

    async def __aenter__(self):
        if self.exc:
            raise self.exc
        return self.target

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class FakeClientSession:
    """Fake aiohttp.ClientSession for deterministic unit testing."""
    def __init__(self, response_target):
        self.response_target = response_target
        self.post_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if isinstance(self.response_target, FakeAsyncContextManager):
            return self.response_target
        return FakeAsyncContextManager(target=self.response_target)


class TestParseBypassResponse(unittest.TestCase):
    """Test response parser contracts and mapping."""

    def test_success_with_destination_url(self):
        payload = {"status": "success", "destination_url": "https://mediafire.com/file123"}
        ok, dest, err = bot_mod.parse_bypass_response(payload)
        self.assertTrue(ok)
        self.assertEqual(dest, "https://mediafire.com/file123")
        self.assertIsNone(err)

    def test_success_with_alternative_keys(self):
        # destination key
        payload = {"status": "ok", "destination": "https://mega.nz/file456"}
        ok, dest, err = bot_mod.parse_bypass_response(payload)
        self.assertTrue(ok)
        self.assertEqual(dest, "https://mega.nz/file456")
        self.assertIsNone(err)

        # final_url key
        payload = {"status": "success", "final_url": "https://drive.google.com/xyz"}
        ok, dest, err = bot_mod.parse_bypass_response(payload)
        self.assertTrue(ok)
        self.assertEqual(dest, "https://drive.google.com/xyz")
        self.assertIsNone(err)

    def test_failed_status_with_error(self):
        payload = {"status": "failed", "error": "Recaptcha solve timeout after 30s"}
        ok, dest, err = bot_mod.parse_bypass_response(payload)
        self.assertFalse(ok)
        self.assertIsNone(dest)
        self.assertEqual(err, "Recaptcha solve timeout after 30s")

    def test_invalid_payload_type(self):
        for invalid in [None, "string", 123, [], False]:
            ok, dest, err = bot_mod.parse_bypass_response(invalid)
            self.assertFalse(ok)
            self.assertIsNone(dest)
            self.assertEqual(err, "Invalid response payload")


class TestFormatEmbedError(unittest.TestCase):
    """Test safety formatting and truncation for Discord embeds."""

    def test_empty_or_none(self):
        self.assertEqual(bot_mod.format_embed_error(None), "Unknown error")
        self.assertEqual(bot_mod.format_embed_error(""), "Unknown error")
        self.assertEqual(bot_mod.format_embed_error("   "), "Unknown error")

    def test_short_error_preserved(self):
        msg = "Socket closed unexpectedly"
        self.assertEqual(bot_mod.format_embed_error(msg), msg)

    def test_long_error_truncated(self):
        long_msg = "A" * 1500
        formatted = bot_mod.format_embed_error(long_msg, max_len=1000)
        self.assertEqual(len(formatted), 1000)
        self.assertTrue(formatted.endswith("..."))
        self.assertEqual(formatted[:997], "A" * 997)


class TestCallEngineBypass(unittest.IsolatedAsyncioTestCase):
    """Test call_engine_bypass contract with mocked aiohttp."""

    async def test_empty_url_rejected(self):
        res = await bot_mod.call_engine_bypass("alias123", "")
        self.assertEqual(res["status"], "failed")
        self.assertIn("URL cannot be empty", res["error"])

        res2 = await bot_mod.call_engine_bypass("alias123", "   ")
        self.assertEqual(res2["status"], "failed")
        self.assertIn("URL cannot be empty", res2["error"])

    async def test_successful_bypass_call_with_api_key(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "status": "success",
            "destination_url": "https://example.com/target"
        })

        session = FakeClientSession(response_target=mock_resp)
        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession.return_value = FakeAsyncContextManager(session)
        mock_aiohttp.ClientTimeout = MagicMock()

        with patch.dict(os.environ, {"L4M_API_KEY": "secret-token-123", "L4M_ENGINE_URL": "http://127.0.0.1:8080"}):
            with patch.object(bot_mod, "aiohttp", mock_aiohttp):
                with patch.object(bot_mod, "ENGINE_API_URL", "http://127.0.0.1:8080"):
                    result = await bot_mod.call_engine_bypass("xyz123", "https://link4m.net/go/xyz123")

        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("destination_url"), "https://example.com/target")

        # Verify post arguments
        self.assertEqual(len(session.post_calls), 1)
        url_arg, kwargs = session.post_calls[0]
        self.assertEqual(url_arg, "http://127.0.0.1:8080/api/v1/bypass")
        payload = kwargs.get("json", {})
        self.assertEqual(payload.get("url"), "https://link4m.net/go/xyz123")
        self.assertEqual(payload.get("alias"), "xyz123")
        self.assertTrue(payload.get("wait"))

        headers = kwargs.get("headers", {})
        self.assertEqual(headers.get("x-api-key"), "secret-token-123")
        self.assertEqual(headers.get("Authorization"), "Bearer secret-token-123")

    async def test_non_json_502_html_response_handled_gracefully(self):
        mock_resp = MagicMock()
        mock_resp.status = 502
        mock_resp.text = AsyncMock(return_value="<html><body>502 Bad Gateway</body></html>")

        session = FakeClientSession(response_target=mock_resp)
        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession.return_value = FakeAsyncContextManager(session)
        mock_aiohttp.ClientTimeout = MagicMock()

        with patch.object(bot_mod, "aiohttp", mock_aiohttp):
            result = await bot_mod.call_engine_bypass("alias1", "https://link4m.net/go/alias1")

        self.assertEqual(result.get("status"), "failed")
        self.assertIn("HTTP 502", result.get("error", ""))
        self.assertIn("502 Bad Gateway", result.get("error", ""))

    async def test_200_with_malformed_json_response(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(side_effect=Exception("Invalid JSON"))
        mock_resp.text = AsyncMock(return_value="Not valid json string")

        session = FakeClientSession(response_target=mock_resp)
        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession.return_value = FakeAsyncContextManager(session)
        mock_aiohttp.ClientTimeout = MagicMock()

        with patch.object(bot_mod, "aiohttp", mock_aiohttp):
            result = await bot_mod.call_engine_bypass("alias1", "https://link4m.net/go/alias1")

        self.assertEqual(result.get("status"), "failed")
        self.assertIn("Invalid JSON response", result.get("error", ""))

    async def test_connection_timeout_handling(self):
        import asyncio

        timeout_cm = FakeAsyncContextManager(exc=asyncio.TimeoutError())
        session = FakeClientSession(response_target=timeout_cm)
        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession.return_value = FakeAsyncContextManager(session)
        mock_aiohttp.ClientTimeout = MagicMock()

        with patch.object(bot_mod, "aiohttp", mock_aiohttp):
            result = await bot_mod.call_engine_bypass("alias1", "https://link4m.net/go/alias1")

        self.assertEqual(result.get("status"), "failed")
        self.assertIn("timed out", result.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
