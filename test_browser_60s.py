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
        if 'what-on.com' in req.url and any(k in req.url for k in ['client', 'get_quest_code']):
            print('[Req]', req.method, req.url[:120])

    def on_resp(resp):
        if 'what-on.com' in resp.url and 'get_quest_code' in resp.url:
            print('[Resp Body]', resp.text())

    page = context.new_page()
    page.on('request', on_req)
    page.on('response', on_resp)

    # Prevent timer from pausing on blur
    page.add_init_script('''
        Object.defineProperty(document, 'hidden', { get: () => false });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        window.addEventListener('blur', (e) => e.stopImmediatePropagation(), true);
    ''')

    print("[1] Navigating to https://tylenhacai100.io ...")
    page.goto('https://tylenhacai100.io', wait_until='domcontentloaded')
    time.sleep(3)

    btn = page.query_selector('div[id="5zqDZ7qw"] button')
    if btn:
        print("[2] Found button, clicking to start 60s countdown...")
        btn.click()

        for sec in range(70):
            time.sleep(1)
            b = page.query_selector('div[id="5zqDZ7qw"]')
            text = b.inner_text().strip() if b else ""
            if sec % 10 == 0 or "Mã" in text or "sau" in text:
                print(f"  [{sec}s] State: {text}")
            if "Mã KM" in text or (len(text) == 6 and text.isalnum()):
                print("\n🎉 SPONSOR CODE REVEALED IN BROWSER:", text)
                with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/sponsor_code.txt', 'w', encoding='utf-8') as f:
                    f.write(text)
                break
    else:
        print("[!] Button not found!")

    browser.close()
