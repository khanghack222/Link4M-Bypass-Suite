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
    print('Initial class of tile 0:', tiles.first.get_attribute('class'))
    tiles.first.click(force=True)
    for i in range(10):
        time.sleep(0.5)
        cls = tiles.first.get_attribute('class')
        print(f'T+{(i+1)*0.5}s class:', cls)
    browser.close()
