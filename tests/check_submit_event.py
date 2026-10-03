from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    
    res = page.evaluate("""() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('NHẬP MÃ'));
        return {
            btnExists: !!btn,
            onclick: btn ? btn.onclick : null,
            attrs: btn ? btn.getAttributeNames().map(n => ({ name: n, val: btn.getAttribute(n) })) : []
        };
    }""")
    print('res:', res)
    b.close()
