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

    cb = bf.locator('.rc-imageselect, #rc-imageselect')
    print('challenge_box count:', cb.count())
    if cb.count() > 0:
        print('challenge_box bbox:', cb.first.bounding_box())
        table = bf.locator('table.rc-imageselect-table-33, table.rc-imageselect-table-44, .rc-imageselect-target table')
        print('table count:', table.count(), 'bbox:', table.first.bounding_box() if table.count() > 0 else 'none')
    browser.close()
