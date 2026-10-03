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

    final_code = None
    def on_resp(resp):
        global final_code
        if any(k in resp.url for k in ['get_quest_code', 'client.js']):
            try:
                txt = resp.text()
                print(f"[RESP {resp.status}] {resp.url[:100]} -> {txt[:300]}", flush=True)
                data = json.loads(txt)
                if data.get('success') and 'html' in data:
                    code_html = str(data['html'])
                    if 'Vui lòng' not in code_html and len(code_html.strip()) > 0:
                        final_code = code_html.strip()
                        print(f"\n🎉 GOT CONFIRMATION CODE FROM API: {final_code} 🎉\n", flush=True)
            except Exception:
                pass

    pg.on('response', on_resp)

    # First load home to set localStorage tokens from Step 1
    pg.goto('https://tylenhacai.in/')
    pg.evaluate("""() => {
        localStorage.setItem("traffic_pgEZtmBLD2SRQ_quest", JSON.stringify({
            "href": "https://tylenhacai.in/",
            "traffic_session": "6ac0792fd829f9f1a70c67ae",
            "id": "6ac079702906f543620c1fb7",
            "timestamp": Date.now()
        }));
        localStorage.setItem("traffic_pgEZtmBLD2SRQ", "f509706a-2357-4f52-9fd1-55069022b62d");
    }""")

    # Navigate to subpage with hash
    target_sub = 'https://tylenhacai.in/bang-xep-hang#ss-mBLD2SRQ'
    print(f"Navigating to {target_sub} ...", flush=True)
    pg.goto(target_sub)
    pg.wait_for_timeout(3000)

    pg.evaluate("""() => {
        document.querySelectorAll('#hpps-popup, .popup, .modal, .hpps-overlay').forEach(el => el.remove());
    }""")

    # Click Step 2 button
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
    print("Clicked Step 2 button:", clicked, flush=True)

    # Monitor 15s countdown
    start_t = time.time()
    for _ in range(25):
        time.sleep(1)
        txt = pg.evaluate("""() => {
            const el = document.querySelector('#mBLD2SRQ, .whatoncode');
            return el ? el.innerText.trim() : null;
        }""")
        print(f"[{int(time.time() - start_t)}s STEP 2] #mBLD2SRQ: {txt}", flush=True)
        if final_code:
            break
        if txt and ('Mã KM:' in txt or 'Mã:' in txt):
            m = re.search(r'(?:Mã KM:|Mã:)\s*([A-Za-z0-9_\-]+)', txt)
            if m:
                final_code = m.group(1)
                print(f"\n🎉 CODE FROM DOM: {final_code} 🎉\n", flush=True)
                break

    print("Final Code Result:", final_code, flush=True)
    b.close()
