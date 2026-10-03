import sys
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
        // Accelerate setInterval when delay is 100ms
        const origSetInterval = window.setInterval;
        window.setInterval = function(fn, delay) {
            if (delay === 100) {
                return origSetInterval(fn, 2);
            }
            return origSetInterval(fn, delay);
        };
    ''')
    pg = c.new_page()

    def on_resp(r):
        if 'get_quest_code' in r.url or 'client.js' in r.url:
            try:
                print(f"[RESP {r.status}] {r.url[:120]}")
                print(f"BODY: {r.text()[:300]}")
            except Exception as e:
                print(f"Error reading body: {e}")

    pg.on('response', on_resp)
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    pg.wait_for_timeout(2000)
    pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    pg.wait_for_timeout(1000)
    pg.locator('#fC6by7 button').click()
    print('Clicked button!')

    for _ in range(40):
        pg.mouse.wheel(0, 100)
        pg.wait_for_timeout(100)

    pg.wait_for_timeout(3000)
    b.close()
