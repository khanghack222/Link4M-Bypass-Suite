import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    
    page.goto('https://gatekno.net/', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false, browserName: 'Chrome' });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    print("Clicking trade-d-btn...")
    page.click('#trade-d-btn')
    
    for s in range(1, 80):
        time.sleep(1)
        res = page.evaluate("""() => {
            const btn = document.getElementById('trade-d-btn');
            const content = document.getElementById('trade-d-btn__content');
            const copyEl = document.querySelector('.copy-code, #copy-code');
            return {
                btnText: btn ? btn.innerText : null,
                contentHtml: content ? content.innerHTML : null,
                copyText: copyEl ? copyEl.innerText : null
            };
        }""")
        if s > 60 or s % 10 == 0:
            print(f"Sec {s}: {res}")
        if res.get('copyText'):
            print(f"SUCCESS! CODE IS: {res['copyText']}")
            break
    b.close()
