from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    
    page.goto('https://mu88-heyapp.com', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false, browserName: 'Chrome' });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    print("Clicking trade-d-btn...")
    page.click('#trade-d-btn')
    
    # Wait until countdown reaches 0 (66 seconds)
    print("Waiting 66 seconds for countdown to finish...")
    time.sleep(66)
    
    print("Countdown finished! Checking cookies and state:")
    cookies = page.evaluate("() => document.cookie")
    print("Cookies:", cookies)
    
    print("Reloading page...")
    page.reload(wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    time.sleep(2)
    
    # Run btd.js on reloaded page
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false, browserName: 'Chrome' });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    time.sleep(2)
    res = page.evaluate("""() => {
        const btn = document.getElementById('trade-d-btn');
        const copyEl = document.querySelector('.copy-code, #copy-code');
        return {
            btnText: btn ? btn.innerText : null,
            copyText: copyEl ? copyEl.innerText : null
        };
    }""")
    print("After reload result:", res)
    
    b.close()
