import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    page.on('request', lambda r: print(f'[REQ] {r.method} {r.url}') if 'api/code' in r.url else None)
    page.on('response', lambda r: print(f'[RESP {r.status}] {r.url}') if 'api/code' in r.url else None)
    
    page.goto('https://booksvertigoandtea.com/', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    
    # Ensure BTD
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    print("Clicking trade-d-btn...")
    page.click('#trade-d-btn')
    
    for s in range(1, 10):
        time.sleep(1)
        res = page.evaluate("""() => {
            const btn = document.getElementById('trade-d-btn');
            return {
                cls: btn ? btn.className : null,
                text: btn ? btn.innerText : null
            };
        }""")
        print(f"Sec {s}: {res}")
    b.close()
