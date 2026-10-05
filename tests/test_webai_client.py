"""
Unit tests for WebAI-to-API OCR & Vision Integration
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add src and src/core to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_CORE = os.path.join(ROOT, "src", "core")
if SRC_CORE not in sys.path:
    sys.path.insert(0, SRC_CORE)

from webai_client import (
    is_webai_available,
    _call_webai_chat,
    ocr_image_webai,
    resolve_quest_images_webai,
    solve_math_captcha_webai
)


class TestWebAIClient(unittest.TestCase):

    def test_availability_offline(self):
        """When server is offline, should return False without crashing."""
        with patch("webai_client._SESSION.get", side_effect=Exception("Connection refused")):
            avail = is_webai_available(force_check=True)
            self.assertFalse(avail)

    def test_availability_online(self):
        """When server returns 200 on /health, should return True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("webai_client._SESSION.get", return_value=mock_resp):
            avail = is_webai_available(force_check=True)
            self.assertTrue(avail)

    def test_ocr_image_webai(self):
        """Test OCR extraction format and parsing."""
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": "Bước 2: Tìm kiếm 'keo nha cai' trên Google\nBước 3: Vào trang keobongda11.net"
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_response

        with patch("webai_client.is_webai_available", return_value=True):
            with patch("webai_client._SESSION.post", return_value=mock_resp):
                fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
                res = ocr_image_webai(fake_png)
                self.assertIn("keobongda11.net", res)
                self.assertIn("keo nha cai", res)

    def test_resolve_quest_images_webai(self):
        """Test structured mission extraction from images."""
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"keyword": "keo nha cai", "domain_hint": "keobongda11.net", "target_domains": ["keobongda11.net"], "page_hint": 1}\n```'
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_response

        with patch("webai_client.is_webai_available", return_value=True):
            with patch("webai_client._SESSION.post", return_value=mock_resp):
                fake_imgs = [b"\x89PNG\r\n\x1a\n" + b"\x00" * 900]
                quest = resolve_quest_images_webai(fake_imgs)
                self.assertEqual(quest.get("keyword"), "keo nha cai")
                self.assertEqual(quest.get("domain_hint"), "keobongda11.net")
                self.assertEqual(quest.get("target_domains"), ["keobongda11.net"])

    def test_solve_math_captcha_webai(self):
        """Test math captcha answering against multiple choices."""
        fake_response = {
            "choices": [
                {"message": {"content": "8"}}
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_response

        with patch("webai_client.is_webai_available", return_value=True):
            with patch("webai_client._SESSION.post", return_value=mock_resp):
                fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
                ans = solve_math_captcha_webai(fake_png, answers=[2, 4, 8, 12])
                self.assertEqual(ans, 8)


if __name__ == "__main__":
    unittest.main()
