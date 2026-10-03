import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)
    
    recaptcha_target = "#main-form, #recaptcha, #recaptcha-2"
    parts = [s.strip() for s in recaptcha_target.split(",") if s.strip()]
    target_css = ", ".join([f"{p} iframe[src*='recaptcha/api2/anchor'], {p} iframe[src*='recaptcha/enterprise/anchor']" for p in parts])
    
    print("target_css:", target_css)
    anchors = pg.locator(target_css).all()
    print("Found with target_css:", len(anchors))
    for a in anchors:
        print("  Anchor box:", a.bounding_box())
        
    print("All without target_css:", len(pg.locator("iframe[src*='recaptcha/api2/anchor']").all()))
    b.close()
