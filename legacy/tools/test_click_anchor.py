import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    time.sleep(2)

    anchors = page.locator("iframe[src*='recaptcha/api2/anchor']")
    n_anchors = anchors.count()
    print('Anchors total:', n_anchors)
    for idx in range(n_anchors):
        a = anchors.nth(idx)
        print(f'Anchor {idx}: name={a.get_attribute("name")}, visible={a.is_visible()}')
        cf = a.content_frame
        if cf:
            chk = cf.locator('#recaptcha-anchor')
            print(f'  chk count: {chk.count()}, visible={chk.is_visible()}')
            chk.click()
            time.sleep(2)
            print('  After click aria-checked:', chk.get_attribute('aria-checked'))
            bf = page.locator("iframe[src*='recaptcha/api2/bframe']")
            n_bf = bf.count()
            print('  Bframe total:', n_bf)
            for b_idx in range(n_bf):
                b = bf.nth(b_idx)
                print(f'    Bframe {b_idx}: name={b.get_attribute("name")}, visible={b.is_visible()}, bbox={b.bounding_box()}')
    browser.close()
