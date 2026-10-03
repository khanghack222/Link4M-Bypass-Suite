from patchright.sync_api import sync_playwright
import base64
import os

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
    os.makedirs('data', exist_ok=True)
    with open('data/kw_img.png', 'wb') as f:
        f.write(img_bytes)
    print('Saved data/kw_img.png, size:', len(img_bytes))
