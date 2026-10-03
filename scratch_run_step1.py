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

    def on_resp(resp):
        if any(k in resp.url for k in ['get_quest_code', 'client.js']):
            try:
                print(f"\n[NETWORK RESP {resp.status}] {resp.url[:100]} -> {resp.text()[:300]}", flush=True)
            except Exception:
                pass

    pg.on('response', on_resp)

    print("Navigating to https://tylenhacai.in ...", flush=True)
    pg.goto('https://tylenhacai.in', referer='https://www.google.com/')
    pg.wait_for_timeout(3000)

    pg.evaluate("""() => {
        document.querySelectorAll('#hpps-popup, .popup, .modal, .hpps-overlay').forEach(el => el.remove());
    }""")

    # Click button inside #mBLD2SRQ
    clicked = pg.evaluate("""() => {
        let btn = document.querySelector("#mBLD2SRQ button");
        if (!btn) {
            btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('LẤY MÃ'));
        }
        if (btn) {
            btn.click();
            return true;
        }
        return false;
    }""")
    print("Clicked button:", clicked, flush=True)

    # Monitor countdown
    start_t = time.time()
    last_t = ""
    for _ in range(75):
        time.sleep(1)
        txt = pg.evaluate("""() => {
            const el = document.querySelector('#mBLD2SRQ, .whatoncode');
            return el ? el.innerText.trim() : null;
        }""")
        if txt != last_t:
            print(f"[{int(time.time() - start_t)}s] #mBLD2SRQ: {txt}", flush=True)
            last_t = txt
        if txt and ('Mã KM:' in txt or 'bước 2' in txt.lower() or 'click bất kỳ' in txt.lower()):
            break

    # Check localStorage for quest info
    local_storage = pg.evaluate("() => Object.assign({}, localStorage)")
    print("\n[LocalStorage]:", json.dumps(local_storage, indent=2), flush=True)

    b.close()
