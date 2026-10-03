from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on("request", lambda r: print(f"[REQ] {r.method} {r.url} | POST: {r.post_data}") if "gtraffic" in r.url else None)
    page.on("response", lambda r: print(f"[RESP] {r.status} {r.url} | BODY: {r.text()[:200]}") if "gtraffic" in r.url else None)
    page.goto('https://mu88.fund', timeout=25000, wait_until='domcontentloaded')
    time.sleep(2)
    # Scroll down to bottom
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    
    print("Clicking #trade-d-btn...")
    btn = page.locator('#trade-d-btn, .trade-d-btn-container, #avt-d-btn').first
    btn.click(force=True)
    
    for _ in range(8):
        time.sleep(1)
    b.close()
