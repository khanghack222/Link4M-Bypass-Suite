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

    tiles = bf.locator('td.rc-imageselect-tile')
    print('tiles count:', tiles.count())
    t0 = tiles.first
    print('t0 selected before click:', t0.get_attribute('class'))
    t0.click(force=True)
    time.sleep(1)
    print('t0 selected after click:', t0.get_attribute('class'))
    browser.close()
