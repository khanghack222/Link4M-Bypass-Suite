import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    t0 = time.time()
    page.goto('https://link4m.net/go/rrAhXyr', timeout=30000, wait_until='domcontentloaded')
    print(f'Loaded in {time.time()-t0:.2f}s, URL: {page.url}')
    
    time.sleep(3)
    print('Current URL:', page.url)
    print('Title:', page.title())
    
    body = page.evaluate('document.body.innerText')
    print('Body:\n', body[:500])
    b.close()
