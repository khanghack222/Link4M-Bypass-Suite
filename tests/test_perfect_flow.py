from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE {m.type}] {m.text}'))
    page.on('pageerror', lambda e: print(f'[PAGEERROR] {e}'))
    
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
    t0 = time.time()
    page.goto('https://mu88.fund', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    print(f'Page ready in {time.time()-t0:.2f}s')
    
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        andanh_code = f.read()
    page.evaluate(f"(() => {{ {andanh_code} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false });")
    
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        btd_code = f.read()
    page.evaluate(f"(() => {{ {btd_code} }})()")
    
    print('Clicking trade-d-btn...')
    page.click('#trade-d-btn')
    
    for s in range(1, 85):
        time.sleep(1)
        res = page.evaluate("""() => {
            const el = document.querySelector('#trade-d-btn');
            return {
                btnText: el ? el.innerText : null,
                btnCls: el ? el.className : null
            };
        }""")
        if s % 10 == 0 or s > 60:
            print(f'Sec {s}: {res}')
        if api_code:
            print(f'\n====================================')
            print(f'>>> SUCCESS! REAL CODE IS: {api_code} <<<')
            print(f'====================================\n')
            break
    b.close()
