import sys, time, json
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
        if any(k in req.url for k in ['whaton', 'quest', 'get_quest_code', 'traffic', 'api', 'widget']):
            print(f"[REQ] {req.method} {req.url}")

    def on_resp(resp):
        if any(k in resp.url for k in ['whaton', 'quest', 'get_quest_code', 'traffic', 'api', 'widget']):
            try:
                print(f"[RESP {resp.status}] {resp.url[:120]} -> {resp.text()[:300]}")
            except Exception:
                pass

    pg.on('request', on_req)
    pg.on('response', on_resp)

    print("Navigating to https://tylenhacai.in ...")
    pg.goto('https://tylenhacai.in', referer='https://www.google.com/')
    pg.wait_for_timeout(3000)

    pg.evaluate("""() => {
        document.querySelectorAll('#hpps-popup, .popup, .modal, .hpps-overlay').forEach(el => el.remove());
    }""")

    # Find the LẤY MÃ button
    btn = pg.locator("button:has-text('LẤY MÃ')").first
    print("Clicking LẤY MÃ...")
    btn.evaluate("el => el.click()")

    for i in range(20):
        time.sleep(1)
        info = pg.evaluate("""() => {
            const btn = document.querySelector('button.whatoncode') || Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('LẤY MÃ') || b.innerText.includes('giây') || b.innerText.includes('Vui lòng'));
            const w = document.querySelector('.whatoncode');
            return {
                btn_text: btn ? btn.innerText.trim() : null,
                whaton_text: w ? w.innerText.trim() : null
            };
        }""")
        print(f"[{i}s] Info:", info)
        if info.get('btn_text') and ('chờ' in info['btn_text'].lower() or 'giây' in info['btn_text'].lower() or 'mã' in info['btn_text'].lower()):
            break

    b.close()
