import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=25000, wait_until='commit')
    time.sleep(3)
    
    info = page.evaluate("""() => {
        const inp = document.querySelector('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])');
        const btns = Array.from(document.querySelectorAll('button, [role="button"]')).map(b => ({
            text: b.innerText,
            cls: b.className,
            disabled: b.disabled,
            type: b.type
        }));
        const forms = Array.from(document.querySelectorAll('form')).map(f => ({
            action: f.action,
            method: f.method
        }));
        return { inp: !!inp, btns, forms };
    }""")
    print(json.dumps(info, indent=2, ensure_ascii=False))
    b.close()
