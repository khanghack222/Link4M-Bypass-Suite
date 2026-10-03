from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    page.on('request', lambda r: print(f'[REQ] {r.method} {r.url}') if 'gtraffic' in r.url else None)
    page.on('response', lambda r: print(f'[RESP {r.status}] {r.url} headers: {dict(r.headers)}') if 'gtraffic' in r.url else None)
    page.goto('https://mu88.fund', timeout=25000, wait_until='networkidle')
    
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        btd_code = f.read()
    page.evaluate(btd_code)
    
    print('Clicking trade-d-btn...')
    page.click('#trade-d-btn')
    
    for i in range(1, 15):
        time.sleep(1)
        res = page.evaluate('''() => {
            const el = document.querySelector('#trade-d-btn');
            const noti = document.querySelector('#notice-d-time, .notice-d-btn, #trade-d-btn__content');
            return {
                btnText: el ? el.innerText : null,
                notiText: noti ? noti.innerText : null,
                btnCls: el ? el.className : null
            };
        }''')
        print(f'Sec {i}: {res}')
        if 'code' in (res.get('btnCls') or '').lower() or any(c.isdigit() for c in (res.get('btnText') or '')):
            print('Progress detected!')
    b.close()
