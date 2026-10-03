import sys, time, json, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    c.add_init_script('''
        if (navigator.webkitTemporaryStorage) {
            navigator.webkitTemporaryStorage.queryUsageAndQuota = function(cb) {
                cb(0, 100 * 1024 * 1024 * 1024);
            };
        }
        let fakeY = 1000;
        Object.defineProperty(window, 'pageYOffset', {
            get: () => { fakeY += 10; return fakeY; },
            configurable: true
        });
        setInterval(() => {
            window.dispatchEvent(new Event('scroll'));
        }, 400);
    ''')
    pg = c.new_page()

    def on_req(req):
        if any(k in req.url for k in ['whaton', 'quest', 'get_quest_code', 'traffic']):
            print(f"[REQ] {req.url[:120]}")

    def on_resp(resp):
        if any(k in resp.url for k in ['get_quest_code', 'whaton']):
            try:
                print(f"[RESP {resp.status}] {resp.url[:120]} -> {resp.text()[:200]}")
            except Exception:
                pass

    pg.on('request', on_req)
    pg.on('response', on_resp)

    print("Navigating to https://tylenhacai.in ...")
    pg.goto('https://tylenhacai.in', referer='https://www.google.com/')
    pg.wait_for_timeout(3000)

    # Find buttons
    btns = pg.locator("button, a.btn, div.btn").all()
    print(f"Found {len(btns)} buttons:")
    for b_el in btns:
        try:
            txt = b_el.inner_text().strip()
            if txt:
                print(f"  Button: '{txt}'")
        except Exception:
            pass

    # Remove any modal/popup overlays
    pg.evaluate("""() => {
        document.querySelectorAll('#hpps-popup, .popup, .modal, .hpps-overlay').forEach(el => el.remove());
    }""")

    # Check for .whatoncode or button with lay ma
    lay_ma_btn = pg.locator("button:has-text('LẤY MÃ'), button:has-text('lay ma'), button:has-text('MÃ'), .whatoncode button").first
    if lay_ma_btn.count() > 0:
        print("[+] Found 'LẤY MÃ' button! Clicking it with evaluate...")
        lay_ma_btn.evaluate("el => el.click()")
        for i in range(15):
            time.sleep(1)
            w_txt = pg.evaluate("() => { const el = document.querySelector('.whatoncode'); return el ? el.innerText : ''; }")
            if w_txt:
                print(f"  [{i}s] whaton: {w_txt.split(chr(10))[0]}")
    else:
        print("[-] No LẤY MÃ button immediately visible. Searching footer or scrolling to bottom...")
        pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        whaton = pg.locator(".whatoncode").count()
        print(f"  .whatoncode count: {whaton}")

    b.close()
