import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://gcchub.io/', timeout=25000, wait_until='commit')
    time.sleep(3)
    
    info = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('[id*="trade"], [class*="trade"], [id*="traffic"], [class*="traffic"]')).map(b => ({
            id: b.id,
            cls: b.className,
            text: b.innerText
        }));
        const scripts = Array.from(document.querySelectorAll('script')).map(s => s.src || s.innerHTML.substring(0, 100));
        return { btns, scripts: scripts.filter(s => s.includes('trade') || s.includes('traffic') || s.includes('bt') || s.includes('andanh')) };
    }""")
    print("info:", info)
    b.close()
