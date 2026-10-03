from playwright.sync_api import sync_playwright
import time, sys
sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on('response', lambda res: print('[NET]', res.status, res.url) if any(k in res.url for k in ['layma', 'campain', 'session', 'qcaptcha', 'getcode']) else None)
    
    print('[*] Navigating to https://onlinejob.com.co...')
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    
    btn = page.locator("[id='4JilBaPXK']")
    if btn.count() > 0:
        print('[+] Found button 4JilBaPXK! Text:', btn.inner_text())
        btn.scroll_into_view_if_needed()
        btn.click()
        print('[+] Clicked button! Monitoring next 10 seconds...')
        for sec in range(10):
            time.sleep(1)
            t = btn.inner_text()
            print(f'  [T+{sec+1}s] Button text:', t)
            # check if iframe QCaptcha appeared
            iframes = page.locator('iframe').all()
            for f in iframes:
                src = f.get_attribute('src') or ''
                title = f.get_attribute('title') or ''
                if 'captcha' in src.lower() or 'captcha' in title.lower():
                    print('  Found captcha iframe:', title, src[:80])
    browser.close()
