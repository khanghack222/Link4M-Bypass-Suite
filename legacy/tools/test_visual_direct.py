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

    # DO NOT CLICK AUDIO. Look at what happens directly in the visual challenge:
    print("Direct visual challenge check:")
    header = bf.locator('.rc-imageselect-instructions, .rc-imageselect-desc, .rc-imageselect-desc-no-canonical')
    print("Header count:", header.count())
    if header.count() > 0:
        print("Instruction:", header.first.inner_text().strip())
    browser.close()
