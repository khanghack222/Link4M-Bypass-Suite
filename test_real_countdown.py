import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    # Only incognito quota bypass, no fast-forwarding setInterval!
    c.add_init_script('''
        if (navigator.webkitTemporaryStorage) {
            navigator.webkitTemporaryStorage.queryUsageAndQuota = function(cb) {
                cb(0, 100 * 1024 * 1024 * 1024);
            };
        }
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
    print("Navigating to secgroup.vn...")
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    pg.wait_for_timeout(2000)
    pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    pg.wait_for_timeout(1000)
    
    btn = pg.locator('#fC6by7 button')
    if btn.is_visible():
        btn.click()
        print('Clicked button! Starting genuine countdown loop...')
    else:
        print('Button not visible!')
        b.close()
        sys.exit(1)

    # In service-v3.js, traffic_wait_time = 60s.
    # Mouse scroll must happen every few seconds to keep countdown decrementing.
    start_time = time.time()
    while time.time() - start_time < 75:
        # Check current countdown text
        status = pg.evaluate('''() => {
            const whaton = document.querySelector('.whatoncode');
            return whaton ? whaton.innerText : null;
        }''')
        elapsed = int(time.time() - start_time)
        print(f"[{elapsed}s] Status: {status}")

        if status and ('Mã KM:' in status or 'id=' in status or 'token' in status):
            print("FOUND CODE / SUCCESS IN STATUS!")
            break

        # Simulate small scroll / wheel
        pg.mouse.wheel(0, 50)
        pg.wait_for_timeout(3000)

    print("Finished wait loop.")
    b.close()
