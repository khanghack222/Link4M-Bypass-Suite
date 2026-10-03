from patchright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://mu88.fund', timeout=25000, wait_until='networkidle')
    res = page.evaluate("""() => {
        const el = document.querySelector('#trade-d-btn');
        return {
            btnExists: !!el,
            btnOuter: el ? el.outerHTML.substring(0, 300) : null,
            cookies: document.cookie,
            hasNexusNoti: !!document.querySelector('.notice-d-btn, #notice-d-btn, [class*="notice"]'),
            allTradeEls: Array.from(document.querySelectorAll('[id*="trade"], [class*="trade"]')).map(x => ({ id: x.id, cls: x.className })),
            allButtons: Array.from(document.querySelectorAll('button, a')).filter(x => (x.innerText || '').includes('LẤY MÃ') || (x.innerText || '').includes('XÁC MINH')).map(x => ({ tag: x.tagName, text: x.innerText, id: x.id, cls: x.className }))
        };
    }""")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    b.close()
