import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        proxy={"server": "http://31.59.20.176:6754", "username": "jorpojes", "password": "8ilov6i8fipk"}
    )
    page = browser.new_page()
    try:
        page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle', timeout=30000)
        a = page.locator('#main-form iframe[src*="recaptcha/api2/anchor"]').first
        a.content_frame.locator('#recaptcha-anchor').click(force=True)
        time.sleep(2)
        bname = 'c-' + a.get_attribute('name')[2:]
        bf = page.locator(f'iframe[name="{bname}"]').first.content_frame
        audio_btn = bf.locator('#recaptcha-audio-button')
        print('audio_btn count with proxy:', audio_btn.count())
        audio_btn.click(force=True)
        time.sleep(2)
        link = bf.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
        print('Download link count with proxy:', link.count())
        if link.count() > 0:
            print('AUDIO URL with proxy:', link.first.get_attribute('href')[:50])
        else:
            err = bf.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message')
            print('Text in bframe with proxy:', err.inner_text() if err.count() > 0 else 'none')
    except Exception as e:
        print('Proxy error:', e)
    browser.close()
