import sys
sys.path.insert(0, 'src/core')
import time
from playwright.sync_api import sync_playwright

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
    print('audio_btn count:', audio_btn.count())
    audio_btn.click(force=True)
    time.sleep(2)
    print('bframe texts:')
    for el in bf.locator('div').all()[:15]:
        t = el.inner_text().strip()
        if t: print(' ', t[:60])
    for btn in bf.locator('button').all():
        print(' btn:', btn.get_attribute('id'), btn.get_attribute('title'), btn.is_visible())
    browser.close()
