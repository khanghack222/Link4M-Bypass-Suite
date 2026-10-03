import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://link4m.net/go/rrAhXyr', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    
    info = page.evaluate("""() => {
        const adv = document.querySelector('#advertise-html-wrapper');
        const recaptcha = document.querySelector('#recaptcha, .g-recaptcha, iframe[src*="recaptcha"]');
        const inputs = Array.from(document.querySelectorAll('input')).map(i => ({ name: i.name, id: i.id, placeholder: i.placeholder, type: i.type }));
        const imgs = Array.from(document.querySelectorAll('#advertise-html-wrapper img, img')).map(img => ({ src: img.src.substring(0, 80), alt: img.alt }));
        const forms = Array.from(document.querySelectorAll('form')).map(f => ({ id: f.id, action: f.action }));
        return {
            hasAdv: !!adv,
            advText: adv ? adv.innerText.substring(0, 300) : null,
            hasRecaptcha: !!recaptcha,
            inputs,
            imgs: imgs.slice(0, 10),
            forms
        };
    }""")
    print(json.dumps(info, indent=2, ensure_ascii=False))
    b.close()
