import sys
sys.path.insert(0, 'src/core')
import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Intercept all network traffic
    all_requests = []
    page.on("request", lambda req: all_requests.append((req.method, req.url)))
    page.on("response", lambda res: print(f"[NET] {res.status} {res.url[:90]}", flush=True) if any(k in res.url for k in ['code', 'traffic', 'quest', 'what-on', 'service', 'widget']) else None)
    page.on("console", lambda msg: print(f"[CONSOLE] {msg.text[:120]}", flush=True))

    print("[*] Loading rikbet9.com...")
    page.goto("https://rikbet9.com", wait_until="domcontentloaded", referer="https://www.google.com/")
    time.sleep(3)

    # Check traffic scripts loaded
    scripts = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('script')).map(s => s.src).filter(Boolean);
    }""")
    print("[*] Scripts on rikbet9.com:")
    for s in scripts:
        if any(k in s for k in ['traffic', 'widget', 'what-on', 'service', 'code']):
            print("  -", s)

    # Click Step 1 button
    btn = page.locator("#support, .traffic-button, [class*='whatoncode']").first
    if btn.count() > 0:
        print("[+] Found button 1, clicking...")
        btn.click()
        time.sleep(2)
        print("[*] LocalStorage after click 1:")
        print(page.evaluate("() => JSON.stringify(localStorage)"))

    browser.close()
