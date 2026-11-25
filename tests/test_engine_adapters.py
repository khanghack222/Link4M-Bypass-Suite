#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for src/core/engine_adapters.py.

Every engine module is stubbed in ``sys.modules``; ``subprocess.run`` is stubbed
for the OctoLink path. No browser, no network, no Node.
"""

import os
import sys
import types

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "src", "core"))

import engine_adapters as adapters


def test_dest_from_shapes():
    cases = [
        ("https://example.com/a", "https://example.com/a"),
        ("  https://example.com/b  ", "https://example.com/b"),
        ("", None),
        (None, None),
        ({"ok": True, "destination": "https://example.com/c"}, "https://example.com/c"),
        ({"success": True, "finalUrl": "https://example.com/d"}, "https://example.com/d"),
        ({"final_url": "https://example.com/e"}, "https://example.com/e"),
        ({"data_link": {"url": "https://example.com/f"}}, "https://example.com/f"),
        ({"data_link": "https://example.com/g"}, "https://example.com/g"),
        ({"ok": False, "destination": "https://example.com/h"}, None),
        ({"success": False, "finalUrl": "https://example.com/i"}, None),
        ({"destination": ""}, None),
        (42, None),
    ]
    for value, expected in cases:
        got = adapters.dest_from(value)
        assert got == expected, f"dest_from({value!r}): expected {expected!r}, got {got!r}"
    print(f"[PASS] dest_from() normalised {len(cases)} shapes")


def _stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def test_adapters_call_stub_engines():
    calls = []

    def make(name, result):
        def fake(*args, **kwargs):
            calls.append((name, args, kwargs))
            return result
        return fake

    _stub("bbmkts_runner", run=make("bbmkts", {"ok": True, "destination": "https://example.com/bb"}))
    _stub("gtraffic_runner", run=make("gtraffic", {"data_link": {"url": "https://example.com/gt"}}))
    _stub("layma_runner", run=make("layma", "https://example.com/lm"))
    _stub("trafficvn_runner", run=make("trafficvn", {"success": True, "finalUrl": "https://example.com/tv"}))
    _stub("bypass", run=make("bypass", {"success": True, "url": "https://example.com/l4"}))
    _stub("link4m_engine", bypass_alias=make("link4m_cdp", {"ok": True, "destination": "https://example.com/cdp"}))

    assert adapters.run_bbmkts("https://bbmkts.com/go/x", headless=False) == "https://example.com/bb"
    assert adapters.run_gtraffic("https://gtraffic.io/x", headless=True) == "https://example.com/gt"
    assert adapters.run_layma("https://layma.net/x", headless=True) == "https://example.com/lm"
    assert adapters.run_trafficvn("https://trafficvn.com/get/x", headless=True) == "https://example.com/tv"
    assert adapters.run_link4m_legacy("https://link4m.net/go/x", headless=True,
                                      proxy="http://p:1") == "https://example.com/l4"
    assert adapters.run_link4m_cdp("2kCcIqn", keep_open=True) == "https://example.com/cdp"

    by_name = {name: (args, kwargs) for name, args, kwargs in calls}
    assert by_name["bbmkts"][0] == ("https://bbmkts.com/go/x",)
    assert by_name["bbmkts"][1]["headless"] is False
    assert by_name["bypass"][1]["proxy"] == "http://p:1"
    assert by_name["link4m_cdp"][1]["keep_open"] is True
    print("[PASS] adapters call stubs with documented kwargs")


def test_octolink_stdout_parsing():
    real_run = adapters.subprocess.run

    class FakeProc:
        def __init__(self, stdout):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def fake_run(cmd, **kwargs):
        assert cmd[0].endswith("node") or os.path.basename(cmd[0]) in ("node", "node.exe")
        assert cmd[1].endswith("octolink_runner.js")
        assert "--json" in cmd
        return FakeProc('log line one\nlog line two\n{"success": true, "finalUrl": "https://example.com/octo"}\n')

    adapters.subprocess.run = fake_run
    try:
        got = adapters.run_octolink("https://octolink.vip/abc", headless=True)
        assert got == "https://example.com/octo", got

        adapters.subprocess.run = lambda *a, **k: FakeProc("just logs\nno json here\n")
        assert adapters.run_octolink("https://octolink.vip/abc") is None

        adapters.subprocess.run = lambda *a, **k: FakeProc('{"success": false}\n')
        assert adapters.run_octolink("https://octolink.vip/abc") is None
    finally:
        adapters.subprocess.run = real_run
    print("[PASS] octolink stdout JSON parsing (and no-JSON tolerance)")


def test_destination_validator_blocks_ads():
    from base_runner import BaseBypassRunner

    class Dummy(BaseBypassRunner):
        engine_name = "DUMMY"

        def execute_flow(self, page, context, target_url):
            return target_url

    dummy = Dummy()
    for pattern in BaseBypassRunner.BLOCKED_DESTINATION_PATTERNS:
        url = f"https://evil.example/{pattern}"
        assert dummy.is_valid_destination(url) is False, f"pattern not blocked: {pattern}"
    assert dummy.is_valid_destination("https://example.com/final") is True
    assert dummy.is_valid_destination("not-a-url") is False
    assert dummy.is_valid_destination(None) is False
    print(f"[PASS] validator blocks {len(BaseBypassRunner.BLOCKED_DESTINATION_PATTERNS)} ad patterns")


if __name__ == "__main__":
    print("=== RUNNING ENGINE ADAPTER TESTS ===")
    test_dest_from_shapes()
    test_adapters_call_stub_engines()
    test_octolink_stdout_parsing()
    test_destination_validator_blocks_ads()
    print("=== ALL ENGINE ADAPTER TESTS PASSED ===")
