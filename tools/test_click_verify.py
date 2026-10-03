import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://google.com/recaptcha/api2/demo', wait_until='networkidle')
    a = page.locator('iframe[src*="recaptcha/api2/anchor"]').first
    a.content_frame.locator('#recaptcha-anchor').click(force=True)
    time.sleep(2)
    bname = 'c-' + a.get_attribute('name')[2:]
    bf = page.locator(f'iframe[name="{bname}"]').first.content_frame

    vb = bf.locator('#recaptcha-verify-button')
    print('Before click text:', repr(vb.inner_text()))
    vb.click()
    time.sleep(2)
    print('After click text:', repr(vb.inner_text()))
    header = bf.locator('.rc-imageselect-instructions, .rc-imageselect-desc-no-canonical, .rc-imageselect-desc')
    if header.count() > 0:
        print('New header:', repr(header.first.inner_text().strip()))
    browser.close()
