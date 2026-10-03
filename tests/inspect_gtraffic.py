from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://gtraffic.io/e_2Qu3i', timeout=25000, wait_until='networkidle')
    time.sleep(2)
    txt = page.evaluate("() => document.body.innerText")
    print("BODY TEXT:")
    for line in txt.splitlines():
        line_s = line.strip()
        if line_s:
            print("  ", line_s.encode('ascii', errors='replace').decode())
    imgs = page.evaluate("() => Array.from(document.querySelectorAll('img')).map(i => i.src)")
    print("IMAGES:")
    for img in imgs:
        print("  ", img)
    page.screenshot(path="data/gtraffic_page.png")
    b.close()
