from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    
    api_code = None
    def handle_resp(r):
        global api_code
        if 'api/code' in r.url:
            print(f'[RESP {r.status}] {r.url}')
            try:
                data = r.json()
                print('API RESPONSE DATA:', data)
                if 'code' in data:
                    api_code = data['code']
            except Exception:
                pass
                
    page.on('response', handle_resp)
    page.goto('https://mu88.fund', timeout=25000, wait_until='networkidle')
    
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        btd_code = f.read()
    page.evaluate(btd_code)
    
    print('Clicking trade-d-btn...')
    page.click('#trade-d-btn')
    
    for s in range(1, 80):
        time.sleep(1)
        if s % 10 == 0 or s > 55:
            res = page.evaluate("""() => {
                const el = document.querySelector('#trade-d-btn');
                return {
                    btnText: el ? el.innerText : null,
                    btnCls: el ? el.className : null
                };
            }""")
            print(f'Sec {s}: {res}')
            if api_code:
                print(f'SUCCESS! CODE IS: {api_code}')
                break
    b.close()
