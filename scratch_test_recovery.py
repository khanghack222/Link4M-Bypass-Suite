from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)
    for a in pg.locator('iframe[src*="recaptcha/api2/anchor"]').all():
        box = a.bounding_box()
        if box and box['y'] > 1000:
            a.content_frame.locator('#recaptcha-anchor').click()
            break
    time.sleep(2)
    for f in pg.frames:
        if 'bframe' in f.url:
            print('Bframe found!')
            btn = f.locator('#recaptcha-audio-button')
            if btn.is_visible():
                btn.click()
                time.sleep(1.5)
                print('After audio click:')
                print('  doscaptcha:', f.locator('.rc-doscaptcha-header-text').count() > 0)
                rel = f.locator('#recaptcha-reload-button')
                print('  reload button visible:', rel.is_visible())
                if rel.is_visible():
                    rel.click()
                    time.sleep(2)
                    print('After reload:')
                    print('  has imageselect:', f.locator('.rc-imageselect').count() > 0)
                    inst = f.locator('.rc-imageselect-instructions').all_inner_texts()
                    print('  instructions:', inst)
    b.close()
