import sys
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src", "core"))
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

from patchright.sync_api import sync_playwright
import time
import base64
import re
from sponsor import get_ocr
from math_utils import VN_MATH_NUMS

def solve_math_text(text: str):
    text = text.lower().replace('=', ' ').replace('?', ' ').strip()
    m = re.search(r'(\d+)\s*([\+\-\*xX/÷])\s*(\d+)', text)
    if m:
        n1 = int(m.group(1))
        op = m.group(2)
        n2 = int(m.group(3))
        if op == '+': return str(n1 + n2)
        if op == '-': return str(n1 - n2)
        if op in ['*', 'x', 'X']: return str(n1 * n2)
        if op in ['/', '÷']: return str(n1 // n2 if n2 != 0 else 0)
    return None

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://fischlubin.at', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    print("Page ready!")
    
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    print("Clicking trade-d-btn...")
    page.click('#trade-d-btn')
    
    for i in range(1, 15):
        time.sleep(1)
        res = page.evaluate("""() => {
            const img = document.getElementById('verify-d-img') || document.querySelector('.verify-d-img');
            const btn = document.getElementById('trade-d-btn');
            return {
                hasImg: !!img,
                srcLen: img?.src?.length || 0,
                btnText: btn?.innerText
            };
        }""")
        print(f"Sec {i}: {res}")
        if res.get('srcLen') and res['srcLen'] > 100:
            print("Found image with len:", res['srcLen'])
            break
    b.close()
