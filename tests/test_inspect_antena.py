import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://antenacatalana.net', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn, #trade-btn-clf, #trade-btn', timeout=15000)
    scripts = page.evaluate("""() => Array.from(document.querySelectorAll('script')).map(s => s.src || s.innerHTML.substring(0, 100))""")
    for s in scripts:
        if s.strip():
            print(' ', s[:120])
    b.close()
