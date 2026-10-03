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
    pg.on('request', lambda r: print(f'REQ: {r.method} {r.url[:120]}') if 'what-on' in r.url else None)
    pg.on('response', lambda r: print(f'RESP: {r.status} {r.url[:120]}') if 'what-on' in r.url else None)
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    pg.wait_for_timeout(2000)
    pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    pg.wait_for_timeout(1000)
    pg.locator('#fC6by7 button').click()
    print('Clicked button!')

    # Simulate wheel
    for _ in range(40):
        pg.mouse.wheel(0, 100)
        pg.wait_for_timeout(100)

    res = pg.evaluate('''() => {
        const whaton = document.querySelector('.whatoncode');
        return { whaton: whaton ? whaton.innerText : null };
    }''')
    print('RESULT AFTER ACCELERATED COUNTDOWN:', res)
    b.close()
