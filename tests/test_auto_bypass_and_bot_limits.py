#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Wave 7: auto_bypass non-interactive CLI guards and Discord bot embed limit safety.
"""

import os
import subprocess
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, ".."))
sys.path.insert(0, os.path.join(_ROOT_DIR, "bot"))

from bot_discord_python import format_embed_error


class TestAutoBypassAndBotLimits(unittest.TestCase):
    def test_format_embed_error_truncation(self):
        """Verify error strings are safely bounded to <= max_len for Discord embeds."""
        short_err = "Connection refused on port 8080"
        self.assertEqual(format_embed_error(short_err, max_len=1000), short_err)

        # Huge 5000-character mock HTML error
        huge_err = "<html><body>" + ("Error Traceback Stack " * 300) + "</body></html>"
        self.assertGreater(len(huge_err), 4000)

        formatted = format_embed_error(huge_err, max_len=1000)
        self.assertEqual(len(formatted), 1000)
        self.assertTrue(formatted.endswith("..."))

        # Empty / None handling
        self.assertEqual(format_embed_error(None), "Unknown error")
        self.assertEqual(format_embed_error("   "), "Unknown error")

    def test_auto_bypass_non_interactive_missing_url(self):
        """Verify auto_bypass.py exits non-zero with error when URL is omitted in non-interactive shell."""
        script_path = os.path.join(_ROOT_DIR, "auto_bypass.py")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

        # Test with DEVNULL
        proc_devnull = subprocess.run(
            [sys.executable, script_path],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )
        self.assertNotEqual(proc_devnull.returncode, 0, "auto_bypass.py must not succeed without URL when stdin is DEVNULL")
        self.assertIn("URL is required", proc_devnull.stderr)

        # Test with PIPE
        proc_pipe = subprocess.run(
            [sys.executable, script_path],
            stdin=subprocess.PIPE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )
        self.assertNotEqual(proc_pipe.returncode, 0, "auto_bypass.py must not succeed without URL when stdin is PIPE")
        self.assertIn("URL is required", proc_pipe.stderr)

    def test_auto_bypass_json_missing_url(self):
        """Verify auto_bypass.py --json exits non-zero when URL is omitted."""
        script_path = os.path.join(_ROOT_DIR, "auto_bypass.py")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            [sys.executable, script_path, "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )
        self.assertNotEqual(proc.returncode, 0, "auto_bypass.py --json must exit non-zero without URL")
        self.assertIn("URL is required", proc.stderr)

    def test_colab_start_sh_syntax(self):
        """Verify deploy/remote/colab-start.sh syntax is valid."""
        if os.name == "nt":
            self.skipTest("Unix bash syntax check requires POSIX shell")
        colab_script = os.path.join(_ROOT_DIR, "deploy/remote/colab-start.sh")
        proc = subprocess.run(["bash", "-n", colab_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Syntax error in colab-start.sh: {proc.stderr}")


if __name__ == "__main__":
    unittest.main()
