import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "core"))
import base64
import json
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time
from sponsor import get_ocr

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://fischlubin.at', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    time.sleep(1)
    
    # Ensure BTD
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    page.click('#trade-d-btn')
    time.sleep(4)
    
    info = page.evaluate("""() => {
        const img = document.getElementById('verify-d-img');
        const opts = Array.from(document.querySelectorAll('.verify-d-option, label, [class*="option"]')).map(l => ({
            text: l.innerText,
            val: l.querySelector('input')?.value
        }));
        return {
            imgSrc: img ? img.src.substring(0, 100) : null,
            fullImg: img ? img.src : null,
            opts: opts
        };
    }""")
    print('imgSrc:', info.get('imgSrc'))
    print('opts:', info.get('opts'))
    
    if info.get('fullImg') and 'base64,' in info['fullImg']:
        b64 = info['fullImg'].split('base64,')[1]
        img_bytes = base64.b64decode(b64)
        ocr = get_ocr()
        res, _ = ocr(img_bytes)
        print('OCR of math captcha:', res)
    b.close()
