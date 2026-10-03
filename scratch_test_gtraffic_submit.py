import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages'))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("request", lambda r: print(f"REQ: {r.method} {r.url} | post={r.post_data[:100] if r.post_data else ''}"))
    page.on("response", lambda r: print(f"RESP: {r.status} {r.url}"))
    page.goto('https://gtraffic.io/X3BR2OQ', wait_until='networkidle')
    
    inp = page.locator('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])').first
    if inp.count() > 0:
        inp.fill("84NW1b8W")
        btn = page.locator('button:has-text("NHẬP MÃ XÁC NHẬN")').first
        print("Clicking submit with test code...")
        btn.click()
        page.wait_for_timeout(5000)
    browser.close()
