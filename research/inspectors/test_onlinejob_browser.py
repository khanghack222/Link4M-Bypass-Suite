from playwright.sync_api import sync_playwright
import sys
sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on('response', lambda res: print('[NET]', res.status, res.url) if any(k in res.url for k in ['layma', 'campain', 'session', 'qcaptcha', 'getcode']) else None)
    print('[*] Navigating to https://onlinejob.com.co...')
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    print('[*] Page loaded. Title:', page.title())
    
    # Check for traffic key element or buttons
    btns = page.locator('button, [id*=\"4JilBaPXK\"], .layma, #layma').all()
    print('Buttons found count:', len(btns))
    for b in btns[:10]:
        try:
            print('  btn text:', b.inner_text().strip(), 'id:', b.get_attribute('id'), 'class:', b.get_attribute('class'))
        except:
            pass
    browser.close()
