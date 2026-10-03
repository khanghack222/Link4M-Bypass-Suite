import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('request', lambda r: print(f'[REQ {r.method}] {r.url} | POST: {r.post_data}') if 'gtraffic' in r.url else None)
    page.on('response', lambda r: print(f'[RESP {r.status}] {r.url} | BODY: {r.text()[:200]}') if 'gtraffic' in r.url else None)
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=25000, wait_until='commit')
    time.sleep(3)
    
    inp = page.locator('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])').first
    inp.fill("TEST12345")
    time.sleep(0.5)
    
    btn = page.locator('button:has-text("NHẬP MÃ XÁC NHẬN")').first
    print("Clicking submit button...")
    btn.click()
    time.sleep(3)
    b.close()
