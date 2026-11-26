import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    a = page.locator("#main-form iframe[src*='recaptcha/api2/anchor']").first
    a_name = a.get_attribute("name")
    print(f"Anchor a name: {a_name}")
    chk = a.content_frame.locator("#recaptcha-anchor")
    chk.click(force=True)
    time.sleep(2)

    bframes = page.locator("iframe[src*='recaptcha/api2/bframe']")
    print(f"Bframes count: {bframes.count()}")
    for i in range(bframes.count()):
        bf = bframes.nth(i)
        name = bf.get_attribute("name")
        box = bf.bounding_box()
        b_cf = bf.content_frame
        c_audio = b_cf.locator("#recaptcha-audio-button").count() if b_cf else 0
        print(f"bframe {i}: name={name}, bbox={box}, c_audio={c_audio}")
    browser.close()
