import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    res = page.evaluate("""() => {
        return {
            hasGrecaptcha: typeof grecaptcha !== 'undefined',
            buttons: Array.from(document.querySelectorAll('button')).map(b => ({ text: b.innerText, type: b.type, cls: b.className })),
            vueMounted: !!document.querySelector('#__nuxt')?.__vue_app__
        };
    }""")
    print('res:', json.dumps(res, indent=2, ensure_ascii=False))
    b.close()
