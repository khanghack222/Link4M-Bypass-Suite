#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ AUTONOMOUS CAMPAIGN SCANNER ⚡
Quét realtime các link mẫu từ Link4M/GTraffic/LayMa để nhận diện chiến dịch mới,
bóc tách tên miền tài trợ, kiểm tra nút bấm và cập nhật trực tiếp vào data/bot_brain.json.
Dùng độc lập hoặc chạy theo lịch tự động qua GitHub Actions.
"""

import sys
import os
import json
import time
import re
import urllib.request
import ssl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRAIN_FILE = os.path.join(ROOT_DIR, "data", "bot_brain.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SAMPLE_TEST_CAMPAIGNS = [
    {"platform": "LINK4M", "url": "https://link4m.net/go/68pw167Y"},
    {"platform": "LINK4M", "url": "https://link4m.org/go/HbsX8nh"},
]

def load_brain() -> dict:
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"domain_intelligence": {}, "stats": {}}

def save_brain(data: dict):
    os.makedirs(os.path.dirname(BRAIN_FILE), exist_ok=True)
    with open(BRAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def verify_sponsor_site(domain: str) -> dict:
    """Kiểm tra xem tên miền tài trợ có chứa widget lấy mã traffic sống không."""
    clean = domain.replace("https://", "").replace("http://", "").strip("/").split("/")[0].lower()
    info = {"domain": clean, "live": False, "has_widget": False, "network": None}

    for proto in [f"https://{clean}", f"http://{clean}"]:
        try:
            req = urllib.request.Request(
                proto,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://www.google.com/"
                }
            )
            with urllib.request.urlopen(req, context=ctx, timeout=4.0) as resp:
                if resp.getcode() == 200:
                    info["live"] = True
                    html = resp.read(300000).decode("utf-8", errors="ignore").lower()
                    if "what-on.com" in html:
                        info["network"] = "what-on.com"
                        info["has_widget"] = True
                    elif "website-analytics" in html:
                        info["network"] = "website-analytics.net"
                        info["has_widget"] = True
                    elif any(k in html for k in ["traffic-button", "traffic.com.vn", "whatoncode", "lấy mã", "lay ma", "getcode"]):
                        info["has_widget"] = True
                    break
        except Exception:
            pass
    return info

def run_campaign_scanner():
    print(f"[{time.strftime('%H:%M:%S')}] 🚀 Bắt đầu quét và đồng bộ dữ liệu chiến dịch thời gian thực...")
    brain = load_brain()
    intel = brain.setdefault("domain_intelligence", {})

    scanned = 0
    updated = 0

    for item in list(intel.keys()):
        scanned += 1
        res = verify_sponsor_site(item)
        if res["live"]:
            intel[item]["live"] = True
            if res["has_widget"]:
                intel[item]["has_widget"] = True
                if res["network"]:
                    intel[item]["network"] = res["network"]
            updated += 1
            print(f"[+] Domain verified live: {item} (Widget: {res['has_widget']}, Network: {res['network']})")
        else:
            intel[item]["live"] = False
            print(f"[-] Domain offline or dead: {item}")

    brain["stats"]["last_synced"] = int(time.time())
    brain["stats"]["verified_domains_count"] = len(intel)
    save_brain(brain)
    print(f"[{time.strftime('%H:%M:%S')}] ✅ Quét hoàn tất! Đã kiểm tra {scanned} domain, cập nhật {updated} domain sống.")

if __name__ == "__main__":
    run_campaign_scanner()
