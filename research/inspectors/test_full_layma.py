import sys, os, time, re, requests
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright
from rapidocr_onnxruntime import RapidOCR

print('[*] Starting LayMa E2E Test...')
ocr_engine = RapidOCR()

target_url = 'https://layma.net/Kd1onyItr'
token = 'Kd1onyItr'

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
        ]
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 720}
    )
    
    # 1. Anti-blur & Anti-tab switch script
    context.add_init_script('''
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
        window.hasFocus = () => true;
        ['visibilitychange', 'webkitvisibilitychange', 'blur'].forEach(e => {
            window.addEventListener(e, ev => ev.stopImmediatePropagation(), true);
            document.addEventListener(e, ev => ev.stopImmediatePropagation(), true);
        });
    ''')
    
    # 2. Open LayMa page
    page_layma = context.new_page()
    print(f'[*] Navigating to LayMa: {target_url}...')
    page_layma.goto(target_url, wait_until='networkidle')
    
    # Extract campainId
    camp_el = page_layma.locator('#campainId')
    camp_id = camp_el.inner_text().strip() if camp_el.count() > 0 else ''
    print(f'[+] Extracted campainId: {camp_id}')
    
    # Get hint image
    hint_url = f'https://layma.net/{token}/url-hint?c={camp_id}'
    print(f'[*] Downloading hint image: {hint_url}...')
    hint_cookies = {c['name']: c['value'] for c in context.cookies()}
    r_hint = requests.get(hint_url, cookies=hint_cookies, headers={'User-Agent': 'Mozilla/5.0', 'Referer': target_url})
    
    sponsor_domain = None
    if r_hint.status_code == 200 and len(r_hint.content) > 100:
        with open('temp_hint.png', 'wb') as f:
            f.write(r_hint.content)
        ocr_res, _ = ocr_engine('temp_hint.png')
        if ocr_res:
            for item in ocr_res:
                txt = item[1].strip()
                if '.' in txt and not txt.startswith('http'):
                    sponsor_domain = txt.replace(' ', '')
                    break
    
    if not sponsor_domain:
        sponsor_domain = 'onlinejob.com.co'
    
    print(f'[🎉] Detected Target Sponsor Domain: {sponsor_domain}')
    
    # 3. Open Sponsor Page
    page_sponsor = context.new_page()
    
    # Route Traffic JS to neutralize incognito detection
    def route_traffic_js(route):
        res = route.fetch()
        text = res.text()
        text = text.replace(
            'var detectIncognito = function () {',
            'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: \"Chrome\" }); }; var _old_detect = function() {'
        )
        route.fulfill(response=res, body=text)
    
    page_sponsor.route('**/Traffic/Index/*', route_traffic_js)
    
    extracted_code = None
    def on_sponsor_response(res):
        global extracted_code
        if 'getcode' in res.url:
            try:
                data = res.json()
                print('[+] Intercepted getcode API response:', data)
                if data.get('html'):
                    extracted_code = data.get('html')
            except:
                pass
    page_sponsor.on('response', on_sponsor_response)
    
    sp_url = f'https://{sponsor_domain}'
    print(f'[*] Navigating to sponsor page: {sp_url}...')
    page_sponsor.goto(sp_url, wait_until='networkidle')
    
    # Find button and click
    btn_span = page_sponsor.locator('[id] span:has-text(\"LẤY MÃ\"), [id] span').first
    if btn_span.count() > 0:
        btn_span.scroll_into_view_if_needed()
        time.sleep(0.5)
        btn_span.click(force=True)
        print('[+] Clicked LẤY MÃ button! Starting countdown monitor...')
    
    # Countdown loop
    for tick in range(120):
        time.sleep(1)
        # Check countdown text
        cnt_text = page_sponsor.evaluate('''() => {
            const el = document.querySelector('[id*=\"Ran\"], [id] [class*=\"show_code\"], [id]');
            for (const span of document.querySelectorAll('span, div')) {
                if (/Lấy mã sau\\s*\\d+/i.test(span.innerText)) return span.innerText;
            }
            return null;
        }''')
        if cnt_text:
            m = re.search(r'\\d+', cnt_text)
            rem = m.group(0) if m else '?'
            if tick % 5 == 0 or int(rem) <= 5:
                print(f'  ⌛ Đếm ngược: còn {rem}s (Text: {cnt_text})')
        else:
            print(f'  [*] Tick {tick+1}: No countdown text yet')
            
        if extracted_code:
            break
            
    print('[+] Final extracted code:', extracted_code)
    browser.close()
