import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://booksvertigoandtea.com/', timeout=25000, wait_until='commit')
    page.wait_for_selector('[id*="trade"], [class*="trade"]', timeout=15000)
    print("Page ready! URL:", page.url)
    
    scripts = page.evaluate("""() => Array.from(document.querySelectorAll('script')).map(s => s.src || s.innerHTML.substring(0, 100))""")
    for s in scripts:
        if s.strip():
            print(' ', s[:120])
            
    btns = page.evaluate("""() => Array.from(document.querySelectorAll('[id*="trade"], [class*="trade"]')).map(b => ({ id: b.id, cls: b.className, text: b.innerText }))""")
    print('Buttons:', btns)
    b.close()
