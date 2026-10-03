import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    
    # 1. Bypass Incognito detection (storage quota)
    # 2. Automatically dispatch mousewheel/scroll with alternating offset to keep mouse_scroll active
    c.add_init_script('''
        if (navigator.webkitTemporaryStorage) {
            navigator.webkitTemporaryStorage.queryUsageAndQuota = function(cb) {
                cb(0, 100 * 1024 * 1024 * 1024);
            };
        }
        // Continuous scroll pulse to satisfy service-v3.js mouseScroll
        let offsetCounter = 100;
        setInterval(() => {
            offsetCounter = (offsetCounter === 100) ? 200 : 100;
            window.dispatchEvent(new Event('scroll'));
            window.dispatchEvent(new WheelEvent('mousewheel', { deltaY: offsetCounter }));
        }, 800);
    ''')
    pg = c.new_page()

    def on_resp(r):
        if 'get_quest_code' in r.url or 'client.js' in r.url:
            try:
                print(f"\n[RESP {r.status}] {r.url[:120]}")
                print(f"BODY: {r.text()[:400]}")
            except Exception as e:
                print(f"Error: {e}")

    pg.on('response', on_resp)
    print("Navigating to secgroup.vn...")
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    pg.wait_for_timeout(2000)
    pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    pg.wait_for_timeout(1000)

    btn = pg.locator('#fC6by7 button')
    if btn.is_visible():
        btn.click()
        print('Clicked LẤY MÃ button! Monitoring full 65s countdown...')
    else:
        print('Button not found!')
        b.close()
        sys.exit(1)

    start = time.time()
    last_text = ""
    while time.time() - start < 80:
        time.sleep(2)
        status = pg.evaluate('''() => {
            const whaton = document.querySelector('.whatoncode');
            const el = document.getElementById('fC6by7');
            return {
                whaton: whaton ? whaton.innerText : null,
                dataset: el ? {...el.dataset} : null
            };
        }''')
        cur_text = status.get('whaton') or ""
        first_line = cur_text.split('\n')[0] if cur_text else ""
        if first_line != last_text:
            print(f"[{int(time.time() - start)}s] {first_line}")
            last_text = first_line

        if 'Mã KM:' in cur_text or 'Đã sao chép' in cur_text:
            print("\n>>> CODE REVEALED IN WIDGET! <<<")
            print(cur_text)
            break

    b.close()
