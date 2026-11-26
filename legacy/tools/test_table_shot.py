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
    table = bf.locator('table.rc-imageselect-table-33, table.rc-imageselect-table-44, .rc-imageselect-target table').first
    table.screenshot(path='data/temp/table_test.png')
    print('Table screenshot saved! Size:', len(open('data/temp/table_test.png', 'rb').read()))
    browser.close()
