#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ UNIFIED BASE RUNNER IMPLEMENTATIONS FOR LINK4M BYPASS SUITE ⚡
Wraps domain runners with pre-flight fast paths and standardized execution.
"""

import urllib.request
import urllib.parse
import json
import base64
from typing import Optional

from base_runner import BaseBypassRunner, BypassResult
from runner_registry import register_runner
from errors import DestinationNotFound

@register_runner("BBMKTS")
class BBMKTSRunner(BaseBypassRunner):
    engine_name = "BBMKTS"

    def pre_flight(self, target_url: str) -> Optional[str]:
        if "/go/file/" in target_url and any(k in target_url.lower() for k in ["bbmkts", "bbmkt", "yeumoney"]):
            encoded = target_url.split("/go/file/")[-1].split("?")[0].split("#")[0].strip("/")
            # Attempt url unquote
            try:
                dec = urllib.parse.unquote(encoded)
                if dec.startswith("http") and "bbmkts.com/go/file/" not in dec and self.is_valid_destination(dec):
                    return dec
            except Exception:
                pass
            # Attempt base64 decode with dynamic padding
            try:
                pad = (-len(encoded)) % 4
                dec = base64.b64decode(encoded + ("=" * pad)).decode("utf-8", errors="ignore")
                if dec.startswith("http") and "bbmkts.com/go/file/" not in dec and self.is_valid_destination(dec):
                    return dec
            except Exception:
                pass
        # Try raw base64 unpad if query param or path has encoded payload
        try:
            parsed = urllib.parse.urlparse(target_url)
            qs = urllib.parse.parse_qs(parsed.query)
            for k in ["url", "link", "target", "dest", "file"]:
                if k in qs and qs[k]:
                    val = qs[k][0]
                    if val.startswith("http") and self.is_valid_destination(val):
                        return val
                    try:
                        pad = (-len(val)) % 4
                        d_val = base64.b64decode(val + ("=" * pad)).decode("utf-8", errors="ignore")
                        if d_val.startswith("http") and self.is_valid_destination(d_val):
                            return d_val
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def execute_flow(self, page, context, target_url: str) -> str:
        import bbmkts_runner
        res = bbmkts_runner.run(target_url, headless=True)
        if res and self.is_valid_destination(res):
            return res
        raise DestinationNotFound(f"BBMKTS failed to extract destination for {target_url}")

@register_runner("GTRAFFIC")
class GTrafficRunner(BaseBypassRunner):
    engine_name = "GTRAFFIC"

    def pre_flight(self, target_url: str) -> Optional[str]:
        try:
            is_direct = "direct.gtraffic.io" in target_url or "dr-client" in target_url
            slug = target_url.split("?")[0].split("#")[0].strip().rstrip("/").split("/")[-1]
            probe_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": target_url,
                "Content-Type": "application/json"
            }
            if is_direct:
                api_url = f"https://dr-client.gtraffic.io/api/url/get?id={slug}&deviceType=desktop"
            else:
                api_url = f"https://client.gtraffic.io/api/url/get?id={slug}&deviceType=desktop"

            d_req = urllib.request.Request(api_url, headers=probe_headers)
            with urllib.request.urlopen(d_req, timeout=3) as d_res:
                get_data = json.loads(d_res.read().decode("utf-8", errors="ignore"))

            if get_data:
                dl = get_data.get("data_link")
                direct_leak = None
                if isinstance(dl, dict) and dl.get("url"):
                    direct_leak = dl.get("url")
                elif isinstance(dl, str) and dl.startswith("http"):
                    direct_leak = dl
                if direct_leak and "gtraffic.io" not in direct_leak and self.is_valid_destination(direct_leak):
                    return direct_leak
        except Exception:
            pass
        return None

    def execute_flow(self, page, context, target_url: str) -> str:
        import gtraffic_runner
        res = gtraffic_runner.run(target_url, headless=True)
        if res and self.is_valid_destination(res):
            return res
        raise DestinationNotFound(f"GTraffic failed to extract destination for {target_url}")

@register_runner("LINK4M")
class Link4MRunner(BaseBypassRunner):
    engine_name = "LINK4M"

    def pre_flight(self, target_url: str) -> Optional[str]:
        # Fast extraction if link4m passes target via direct query or redirect parameter
        try:
            parsed = urllib.parse.urlparse(target_url)
            qs = urllib.parse.parse_qs(parsed.query)
            for k in ["dest", "target", "url", "redirect", "go"]:
                if k in qs and qs[k]:
                    val = qs[k][0]
                    if val.startswith("http") and self.is_valid_destination(val):
                        return val
                    try:
                        pad = (-len(val)) % 4
                        d_val = base64.b64decode(val + ("=" * pad)).decode("utf-8", errors="ignore")
                        if d_val.startswith("http") and self.is_valid_destination(d_val):
                            return d_val
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def execute_flow(self, page, context, target_url: str) -> str:
        import bypass
        res = bypass.run(target_url, headless=True)
        if res and self.is_valid_destination(res):
            return res
        raise DestinationNotFound(f"Link4M failed to extract destination for {target_url}")

@register_runner("LAYMA")
class LayMaRunner(BaseBypassRunner):
    engine_name = "LAYMA"

    def execute_flow(self, page, context, target_url: str) -> str:
        import layma_runner
        res = layma_runner.run(target_url, headless=True)
        if res and self.is_valid_destination(res):
            return res
        raise DestinationNotFound(f"LayMa failed to extract destination for {target_url}")

@register_runner("OCTOLINK")
class OctoLinkRunner(BaseBypassRunner):
    engine_name = "OCTOLINK"

    def pre_flight(self, target_url: str) -> Optional[str]:
        # Fast decode nếu là link direct /go/file/ hoặc có encoded parameter
        try:
            from decode_link import decode_file_url
            dest = decode_file_url(target_url)
            if dest and self.is_valid_destination(dest):
                return dest
        except Exception:
            pass
        return None

    def execute_flow(self, page, context, target_url: str) -> str:
        import subprocess
        import os
        import sys
        octo_js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "octolink_runner.js")
        if os.path.exists(octo_js):
            try:
                proc = subprocess.run(["node", octo_js, target_url], capture_output=True, text=True, timeout=120)
                dest_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "destination_url.txt")
                if os.path.exists(dest_file):
                    with open(dest_file, "r", encoding="utf-8") as f:
                        dest = f.read().strip()
                        if dest and self.is_valid_destination(dest):
                            return dest
            except Exception:
                pass
        raise DestinationNotFound(f"OctoLink failed to extract destination for {target_url}")

@register_runner("TRAFFICVN")
class TrafficVNRunner(BaseBypassRunner):
    engine_name = "TRAFFICVN"

    def execute_flow(self, page, context, target_url: str) -> str:
        import trafficvn_runner
        res = trafficvn_runner.run(target_url, headless=True)
        if res and self.is_valid_destination(res):
            return res
        raise DestinationNotFound(f"TrafficVN failed to extract destination for {target_url}")


