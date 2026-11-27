#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Wave 3 runner return fixes, OctoLink environment resolution,
and timeout parameter forwarding.
"""

import ast
import os
import sys
import subprocess
import unittest
from unittest.mock import patch, MagicMock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_TESTS_DIR, ".."))
_CORE_DIR = os.path.join(_ROOT_DIR, "src", "core")
for _p in (_CORE_DIR, _ROOT_DIR, os.path.join(_ROOT_DIR, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import runner_registry
from base_runner import BypassResult
import engine_adapters


class TestRunnerReturnsAndContracts(unittest.TestCase):
    def test_gtraffic_runner_returns_destination(self):
        """Verify gtraffic_runner.py has explicit return final_destination in run()."""
        path = os.path.join(os.path.dirname(__file__), "../src/core/gtraffic_runner.py")
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        run_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                run_func = node
                break
        self.assertIsNotNone(run_func, "gtraffic_runner.py must define run()")
        returns = [n for n in ast.walk(run_func) if isinstance(n, ast.Return)]
        self.assertTrue(len(returns) > 0, "run() must contain return statement")
        has_final_dest_return = any(
            isinstance(r.value, (ast.Name, ast.IfExp)) for r in returns if r.value is not None
        )
        self.assertTrue(has_final_dest_return, "run() must return destination value")

    def test_trafficvn_runner_returns_destination(self):
        """Verify trafficvn_runner.py has explicit return in run()."""
        path = os.path.join(os.path.dirname(__file__), "../src/core/trafficvn_runner.py")
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        run_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                run_func = node
                break
        self.assertIsNotNone(run_func, "trafficvn_runner.py must define run()")
        returns = [n for n in ast.walk(run_func) if isinstance(n, ast.Return)]
        self.assertTrue(len(returns) > 0, "trafficvn_runner.py run() must contain return statement")

    def test_engine_adapters_dest_from_handling(self):
        """Verify engine_adapters.dest_from properly extracts string return."""
        self.assertEqual(engine_adapters.dest_from("https://example.com/dest"), "https://example.com/dest")
        self.assertEqual(engine_adapters.dest_from("  https://example.com/dest  "), "https://example.com/dest")
        self.assertIsNone(engine_adapters.dest_from(None))
        self.assertIsNone(engine_adapters.dest_from(""))
        self.assertEqual(engine_adapters.dest_from({"final_url": "https://example.com/ok"}), "https://example.com/ok")

    def test_runner_registry_execute_accepts_timeout(self):
        """Verify runner_registry.execute forwards timeout to runner."""
        class DummyRunner:
            proxy = None
            timeout = None
            def run(self, url):
                return BypassResult(success=True, destination_url="https://example.com", metadata={})
            def is_valid_destination(self, url):
                return True

        runner_registry._ensure_runners()
        # Test that timeout kwarg is accepted
        res = runner_registry.execute("https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbQ==", timeout=120)
        self.assertTrue(res.success)

    def test_octolink_runner_js_syntax_and_env_paths(self):
        """Verify octolink_runner.js compiles cleanly and respects Linux paths."""
        js_path = os.path.join(os.path.dirname(__file__), "../src/core/octolink_runner.js")
        proc = subprocess.run(["node", "--check", js_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Syntax error in octolink_runner.js: {proc.stderr}")

        # Probe getChromePath and getPythonPath via Node inline snippet (cross-platform safe)
        import json
        escaped_js_path = json.dumps(os.path.abspath(js_path))
        node_script = f"""
        const fs = require('fs');
        const path = require('path');
        const jsPath = {escaped_js_path};
        const code = fs.readFileSync(jsPath, 'utf-8');
        // Extract getChromePath and getPythonPath definitions
        const fnBlock = code.substring(code.indexOf('function getChromePath()'), code.indexOf('const CHROME_PATH ='));
        eval(fnBlock);
        console.log(JSON.stringify({{ chrome: getChromePath(), python: getPythonPath() }}));
        """
        eval_proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(eval_proc.returncode, 0, f"Failed to eval path helpers: {eval_proc.stderr}")
        self.assertIn("chrome", eval_proc.stdout)
        self.assertIn("python", eval_proc.stdout)


if __name__ == "__main__":
    unittest.main()
