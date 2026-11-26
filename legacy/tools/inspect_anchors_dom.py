from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    anchors = page.locator("iframe[src*='recaptcha/api2/anchor']")
    for i in range(anchors.count()):
        a = anchors.nth(i)
        p_info = a.evaluate('el => el.parentElement ? (el.parentElement.id + " " + el.parentElement.className) : ""')
        f_info = a.evaluate('el => el.closest("form") ? (el.closest("form").id + " " + el.closest("form").className) : "none"')
        vis = a.is_visible()
        print(f'Anchor {i}: visible={vis}, parent=[{p_info.strip()}], form=[{f_info.strip()}]')
    browser.close()
