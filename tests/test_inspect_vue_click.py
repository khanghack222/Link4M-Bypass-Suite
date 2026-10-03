from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    page.on('pageerror', lambda e: print(f'[PAGEERROR] {e}'))
    
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    
    # Check if Nuxt app is hydrated
    is_hydrated = page.evaluate("""() => {
        return !!window.__NUXT__;
    }""")
    print('is_hydrated:', is_hydrated)
    
    # Try clicking the change keyword button
    print("Trying click 'ĐỔI TỪ KHÓA MỚI'...")
    btn_change = page.locator('button:has-text("ĐỔI TỪ KHÓA MỚI")').first
    btn_change.click()
    time.sleep(3)
    b.close()
