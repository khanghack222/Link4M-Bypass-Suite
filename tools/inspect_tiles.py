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

    tiles = bf.locator('td.rc-imageselect-tile, .rc-image-tile-target, [role="button"]')
    print('tiles count:', tiles.count())
    for i in range(min(12, tiles.count())):
        t = tiles.nth(i)
        print(f'tile {i}: tag={t.evaluate("el => el.tagName")}, class={t.get_attribute("class")}, bbox={t.bounding_box()}')
    browser.close()
