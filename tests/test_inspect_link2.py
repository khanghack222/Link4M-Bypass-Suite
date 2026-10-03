import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto("https://gtraffic.io/e_2Qu3i", timeout=30000, wait_until="domcontentloaded")
    time.sleep(2)
    
    info = page.evaluate("""() => {
        const imgs = Array.from(document.querySelectorAll('img')).map(i => ({ src: i.src, alt: i.alt, cls: i.className }));
        const forms = Array.from(document.querySelectorAll('form')).map(f => ({ action: f.action, inputs: Array.from(f.querySelectorAll('input')).map(i => ({ name: i.name, type: i.type, id: i.id })) }));
        const spans = Array.from(document.querySelectorAll('b, strong, span, p')).filter(s => (s.innerText || '').includes('hitclub') || (s.innerText || '').includes('Google') || (s.innerText || '').includes('gõ')).map(s => s.innerText);
        return { imgs, forms, spans };
    }""")
    print(json.dumps(info, indent=2, ensure_ascii=False))
    b.close()
