import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        extra_http_headers={'referer': 'https://www.google.com/'}
    )

    def on_req(req):
        if 'what-on.com' in req.url:
            print('[Req]', req.method, req.url[:120])

    def on_resp(resp):
        if 'what-on.com' in resp.url and 'get_quest_code' in resp.url:
            print('[Resp Body]', resp.text())

    page = context.new_page()
    page.on('request', on_req)
    page.on('response', on_resp)

    # SPEED HACK: Patch setInterval to accelerate 60x
    page.add_init_script('''
        Object.defineProperty(document, 'hidden', { get: () => false });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        window.addEventListener('blur', (e) => e.stopImmediatePropagation(), true);

        const origSetInterval = window.setInterval;
        window.setInterval = function(fn, delay) {
            if (delay === 1000) {
                // Accelerate 50x: 1000ms becomes 20ms!
                return origSetInterval(fn, 20);
            }
            return origSetInterval(fn, delay);
        };
    ''')

    print("Navigating with 50x timer speed hack...")
    page.goto('https://tylenhacai100.io', wait_until='domcontentloaded')
    time.sleep(3)

    btn = page.query_selector('div[id="5zqDZ7qw"] button')
    if btn:
        print("Clicking button...")
        btn.click()
        for i in range(15):
            time.sleep(0.5)
            b = page.query_selector('div[id="5zqDZ7qw"]')
            text = b.inner_text().strip() if b else "none"
            print(f"[{i*0.5}s] Text: {text}")
            if "Mã KM" in text or "Lấy mã sau" in text:
                print("🎉 REVEALED:", text)
                break
    else:
        print("Button not found!")

    browser.close()
