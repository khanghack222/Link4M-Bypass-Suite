import sys
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src", "core"))
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

from patchright.sync_api import sync_playwright
import base64
from sponsor import get_ocr

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://gtraffic.io/e_2Qu3i', timeout=30000, wait_until='domcontentloaded')
    src = page.evaluate("""() => {
        const img = document.querySelector('img[alt*="Từ khóa"], img[alt*="nhiệm vụ"]');
        return img ? img.src : null;
    }""")
    b.close()

if src and 'base64,' in src:
    b64_data = src.split('base64,')[1]
    img_bytes = base64.b64decode(b64_data)
    ocr = get_ocr()
    res, _ = ocr(img_bytes)
    print('OCR result:', res)
