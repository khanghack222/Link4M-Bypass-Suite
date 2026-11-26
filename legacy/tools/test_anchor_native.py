from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    time.sleep(2)
    a = page.locator('#main-form iframe[src*="recaptcha/api2/anchor"]').first
    print('Anchor box:', a.bounding_box())
    try:
        a.content_frame.locator('#recaptcha-anchor').click(timeout=3000)
        print('Native click on anchor succeeded!')
    except Exception as e:
        print('Native click failed:', e)
    browser.close()
