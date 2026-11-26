from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    css = '#main-form, #recaptcha, #recaptcha-2'
    parts = [s.strip() for s in css.split(',') if s.strip()]
    target_css = ', '.join([f"{p} iframe[src*='recaptcha/api2/anchor'], {p} iframe[src*='recaptcha/enterprise/anchor']" for p in parts])
    print('target_css:', target_css)
    anchors = page.locator(target_css)
    print('anchors count:', anchors.count())
    for i in range(anchors.count()):
        a = anchors.nth(i)
        print(f'Anchor {i}: box={a.bounding_box()}, name={a.get_attribute("name")}')
    browser.close()
