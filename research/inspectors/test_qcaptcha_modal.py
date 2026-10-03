import sys, time, re
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    traffic_key = None
    def route_traffic_js(route):
        global traffic_key
        res = route.fetch()
        text = res.text()
        m = re.search(r"var\s+traffic_key\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            traffic_key = m.group(1)
            print('[+] Extracted traffic_key from JS:', traffic_key)
        text = text.replace(
            'var detectIncognito = function () {',
            'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {'
        )
        route.fulfill(response=res, body=text)
    
    page.route('**/Traffic/Index/*', route_traffic_js)
    
    print('[*] Navigating to https://onlinejob.com.co...')
    page.goto('https://onlinejob.com.co', wait_until='domcontentloaded')
    time.sleep(2)
    
    print('[+] Current traffic_key:', traffic_key)
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    print('[+] Clicking button...')
    btn_span.click(force=True)
    time.sleep(2)
    
    print('[+] Triggering modal directly...')
    page.evaluate(f"""() => {{
        const el = document.getElementById('{traffic_key}');
        if (typeof showCaptchaModalForGetCode === 'function') {{
            showCaptchaModalForGetCode(el, '1');
        }}
    }}""")
    time.sleep(2)
    
    frames = page.frames
    print('Total frames on page:', len(frames))
    for idx, fr in enumerate(frames):
        print(f'  Frame {idx}: url={fr.url[:80]}, name={fr.name}')
        
    page.screenshot(path='qcaptcha_modal_test.png')
    browser.close()