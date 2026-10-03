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

    vb = bf.locator('#recaptcha-verify-button')
    print('Verify button tag:', vb.evaluate('el => el.outerHTML'))
    print('Verify button disabled:', vb.get_attribute('disabled'))
    print('Verify button class:', vb.get_attribute('class'))
    browser.close()
