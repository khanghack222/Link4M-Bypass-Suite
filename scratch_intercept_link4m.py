import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages'))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    def log_api(res):
        u = res.url
        ct = res.headers.get('content-type', '')
        if 'json' in ct or any(k in u for k in ['campaign', 'get', 'link', 'traffic', 'quest', 'info']):
            try:
                body = res.text()
                print(f"\n[API INTERCEPT] {res.status} {u}")
                print(f"BODY ({len(body)} chars): {body[:800]}")
            except Exception:
                pass
                
    page.on('response', log_api)
    print("Navigating to Link4M...")
    page.goto('https://link4m.net/go/2kCcIqn', wait_until='networkidle')
    page.wait_for_timeout(3000)
    
    # Also dump any global JS variables that hold campaign or link data
    globals_data = page.evaluate("""() => {
        const out = {};
        for (let k of ['campaign', 'link', 'alias', 'traffic', 'data', 'advertise', 'config', 'destination_url']) {
            if (window[k]) out[k] = window[k];
        }
        return out;
    }""")
    print("\n[WINDOW GLOBALS]:", globals_data)
    browser.close()
