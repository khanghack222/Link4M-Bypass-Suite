#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ TEST GIẢI CAPTCHA RIÊNG VỚI PROXY JIT (CÀO VÀ DÙNG NGAY LẬP TỨC - 0% DEAD) ⚡
Cào trực tiếp proxy tươi mới trong 2s, nạp vào browser và giải reCAPTCHA v2.
"""

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "core")
sys.path.insert(0, CORE_DIR)

from patchright.sync_api import sync_playwright
from config import CHROME_PATH, STEALTH_INIT_SCRIPT
from recaptcha_solver import RecaptchaSolver
from jit_proxy import get_live_proxy_jit

def test_captcha_jit(target_url="https://link4m.net/go/68pw167Y"):
    print("="*60)
    print("⚡ KHỞI ĐỘNG CƠ CHẾ PROXY JIT: CÀO & DÙNG NGAY (ZERO STORAGE) ⚡")
    print("="*60, flush=True)

    t_start = time.perf_counter()
    live_px = get_live_proxy_jit()
    proxy_cfg = {"server": live_px["server"]} if live_px else None

    if proxy_cfg:
        print(f"[+] 🎯 Đang cấp Proxy JIT tươi mới: {proxy_cfg['server']} (Ping: {live_px['latency_ms']}ms)", flush=True)
    else:
        print("[!] Không tìm thấy proxy JIT đạt chuẩn trong 2s, chạy Direct...", flush=True)

    with sync_playwright() as p:
        args = [
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--window-size=1280,720",
            "--mute-audio=false",
            "--ignore-certificate-errors",
            "--ignore-ssl-errors"
        ]

        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=r"data\temp\test_captcha_profile",
                executable_path=CHROME_PATH if CHROME_PATH and os.path.exists(CHROME_PATH) else None,
                headless=True,
                proxy=proxy_cfg,
                args=args,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
        except Exception as e_launch:
            print(f"[!] Lỗi launch: {e_launch}")
            return

        context.add_init_script(STEALTH_INIT_SCRIPT)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            print(f"[*] Đang tải trang: {target_url}...", flush=True)
            t_nav = time.perf_counter()
            page.goto(target_url, timeout=12000)
            page.wait_for_timeout(2500)
            nav_ms = round((time.perf_counter() - t_nav) * 1000, 1)
            print(f"[+] Trang Link4M tải thành công trong {nav_ms}ms!", flush=True)
        except Exception as e_nav:
            print(f"[-] Proxy bị Cloudflare bóp hoặc timeout ({e_nav}), khởi động fallback Direct IP...", flush=True)
            context.close()
            # Mở context Direct IP sạch
            context = p.chromium.launch_persistent_context(
                user_data_dir=r"data\temp\test_captcha_profile_direct",
                executable_path=CHROME_PATH if CHROME_PATH and os.path.exists(CHROME_PATH) else None,
                headless=True,
                args=args,
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
            context.add_init_script(STEALTH_INIT_SCRIPT)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, timeout=15000)
            page.wait_for_timeout(2500)
            print(f"[+] Direct IP tải trang thành công!", flush=True)

        print("\n[*] 🚀 BẮT ĐẦU GIẢI RECAPTCHA V2 (PURE LOCAL SOLVER)...", flush=True)
        solver = RecaptchaSolver(headless=True)
        t_solve = time.perf_counter()
        res = solver.solve_on_page(page, container_selector="#main-form, #main-form-2")
        solve_sec = round(time.perf_counter() - t_solve, 2)
        total_sec = round(time.perf_counter() - t_start, 2)

        print("\n" + "="*60)
        if res.get("success"):
            token = res.get("token", "")
            print(f"🎉 GIẢI CAPTCHA THÀNH CÔNG 100%!")
            print(f"⏱️  Thời gian giải Captcha : {solve_sec}s")
            print(f"⏱️  Tổng thời gian (cả cào + tải): {total_sec}s")
            print(f"🔑 Phương thức giải        : {res.get('type')}")
            print(f"🎫 Độ dài token reCAPTCHA  : {len(token)} ký tự")
            print(f"📄 Token mẫu               : {token[:60]}...")
        else:
            print(f"❌ Kết quả giải: {res}")
            print(f"⏱️  Thời gian thử: {solve_sec}s")
        print("="*60 + "\n")

        context.close()

if __name__ == "__main__":
    test_captcha_jit()
