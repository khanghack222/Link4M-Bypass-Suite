from patchright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    page.on('request', lambda r: print(f'[REQ] {r.method} {r.url}') if 'gtraffic' in r.url else None)
    page.on('response', lambda r: print(f'[RESP {r.status}] {r.url} body: {r.text()[:200]}') if 'gtraffic' in r.url else None)
    page.goto('https://mu88.fund', timeout=25000, wait_until='networkidle')
    
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        btd_code = f.read()
    page.evaluate(btd_code)
    page.click('#trade-d-btn')
    time.sleep(3)
    
    # Try calling the code endpoint after 3 seconds
    res = page.evaluate('''async () => {
        try {
            // Find rid (stored in vault or cookies)
            const cookies = document.cookie;
            console.log('cookies:', cookies);
            // Let's see if __browser_challenge_ok or tokens exist
            return { cookies };
        } catch(e) {
            return { error: e.toString() };
        }
    }''')
    print('res:', res)
    b.close()
