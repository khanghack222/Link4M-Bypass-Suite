import sys
import os
sys.path.insert(0, os.path.join(os.path.abspath('.'), 'src', 'core'))
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from patchright.sync_api import sync_playwright
from sponsor import get_ocr

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://gtraffic.io/e_2Qu3i', timeout=30000, wait_until='domcontentloaded')
    loc = page.locator('img[alt*="tim kiem"], img[src*="cdn.gtraffic.io"]').first
    loc.wait_for(timeout=10000)
    img_bytes = loc.screenshot()
    b.close()

ocr = get_ocr()
res, _ = ocr(img_bytes)
print('OCR result:')
for line in res:
    print(' ', line[1])
