import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE {m.type}] {m.text}'))
    page.on('pageerror', lambda e: print(f'[PAGEERROR] {e}'))
    page.on('request', lambda r: print(f'[REQ] {r.method} {r.url}') if 'tracking' in r.url or 'url' in r.url else None)
    page.on('response', lambda r: print(f'[RESP {r.status}] {r.url}') if 'tracking' in r.url or 'url' in r.url else None)
    
    print("Navigating...")
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=25000, wait_until='commit')
    
    print("Waiting for api/url/get ...")
    try:
        page.wait_for_response(lambda r: "api/url/get" in r.url, timeout=20000)
        print("api/url/get finished!")
    except Exception as e:
        print("Wait note:", e)
        
    time.sleep(2)
    
    inp = page.locator('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])').first
    inp.click()
    page.keyboard.type('DW54qX6C', delay=30)
    time.sleep(0.5)
    
    btn = page.locator('button:has-text("NHẬP MÃ XÁC NHẬN")').first
    print("Clicking submit button...")
    btn.click()
    
    for s in range(1, 10):
        time.sleep(1)
        print(f"Sec {s} after click, URL: {page.url}")
    b.close()
