import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core import config


class TestConfigAndCleanup(unittest.TestCase):
    def test_get_chrome_path_respects_chrome_bin_env(self):
        # Create a temporary dummy executable file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"mock binary")
            tmp_path = tmp.name

        try:
            old_env = os.environ.get("CHROME_BIN")
            os.environ["CHROME_BIN"] = tmp_path
            detected = config.get_chrome_path()
            self.assertEqual(detected, tmp_path)
        finally:
            if old_env is not None:
                os.environ["CHROME_BIN"] = old_env
            else:
                os.environ.pop("CHROME_BIN", None)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_get_chrome_path_ignores_nonexistent_chrome_bin(self):
        old_env = os.environ.get("CHROME_BIN")
        os.environ["CHROME_BIN"] = "/nonexistent/path/to/custom/chrome/bin"
        try:
            detected = config.get_chrome_path()
            self.assertNotEqual(detected, "/nonexistent/path/to/custom/chrome/bin")
        finally:
            if old_env is not None:
                os.environ["CHROME_BIN"] = old_env
            else:
                os.environ.pop("CHROME_BIN", None)


if __name__ == "__main__":
    unittest.main()
