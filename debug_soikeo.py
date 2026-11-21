import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    context = browser.new_context()
    page = context.new_page()

    # Capture console and dialogs
    page.on('console', lambda msg: print(f'[Console {msg.type}] {msg.text}'))
    page.on('pageerror', lambda err: print(f'[PageError] {err}'))

    page.on('request', lambda r: print(f'[Req] {r.method} {r.url[:120]}') if 'what-on' in r.url else None)
    page.on('response', lambda r: print(f'[Resp {r.status}] {r.url[:120]}') if 'what-on' in r.url else None)

    print("Navigating...")
    page.goto('https://soikeobongda.life', wait_until='networkidle')
    
    # Check button
    btn = page.query_selector('button:has-text("LẤY MÃ")')
    if btn:
        print("Found button HTML:", btn.evaluate('el => el.outerHTML'))
        parent = btn.evaluate('el => el.parentElement.outerHTML')
        print("Parent HTML:", parent[:300])
        print("Clicking button...")
        btn.click()
        time.sleep(5)
        print("After 5s parent HTML:", btn.evaluate('el => el.parentElement.innerHTML'))
    else:
        print("Button not found!")

    browser.close()
