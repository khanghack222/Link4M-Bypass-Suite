import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    a = page.locator('#main-form iframe[src*="recaptcha/api2/anchor"]').first
    a.content_frame.locator('#recaptcha-anchor').click(force=True)
    time.sleep(2)
    bname = 'c-' + a.get_attribute('name')[2:]
    bf = page.locator(f'iframe[name="{bname}"]').first.content_frame
    audio_btn = bf.locator('#recaptcha-audio-button')
    print('audio_btn in patchright:', audio_btn.count())
    audio_btn.click(force=True)
    time.sleep(2)
    link = bf.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
    print('Download link count in patchright:', link.count())
    if link.count() > 0:
        print('AUDIO URL:', link.first.get_attribute('href')[:50])
    else:
        err = bf.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message')
        print('Text in bframe:', err.inner_text() if err.count() > 0 else 'none')
    browser.close()
