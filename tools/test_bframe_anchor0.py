import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    time.sleep(1)

    a0 = page.locator("#main-form iframe[src*='recaptcha/api2/anchor']").first
    print("Clicking a0...")
    chk0 = a0.content_frame.locator("#recaptcha-anchor")
    chk0.click(force=True)
    time.sleep(2)
    print("a0 checked:", chk0.get_attribute("aria-checked"))

    bf = page.locator("iframe[src*='recaptcha/api2/bframe']")
    print("Total bframes:", bf.count())
    for i in range(bf.count()):
        b = bf.nth(i)
        print(f"bframe {i}: name={b.get_attribute('name')}, is_visible={b.is_visible()}, bbox={b.bounding_box()}")
        cf = b.content_frame
        if cf:
            for btn in cf.locator("button").all():
                print(f"  button: id='{btn.get_attribute('id')}', title='{btn.get_attribute('title')}', visible={btn.is_visible()}")
    browser.close()
