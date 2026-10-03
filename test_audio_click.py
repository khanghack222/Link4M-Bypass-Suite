from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)
    
    # Click anchor 1 (#recaptcha-2)
    anchors = pg.locator('iframe[src*="recaptcha/api2/anchor"]').all()
    for a in anchors:
        box = a.bounding_box()
        if box and box['y'] > 1000:
            a.content_frame.locator('#recaptcha-anchor').click()
            print("Clicked anchor at y=", box['y'])
            break
            
    time.sleep(2)
    for idx, f in enumerate(pg.frames):
        if 'bframe' in f.url:
            has_audio = f.locator('#recaptcha-audio-button').count() > 0
            has_vis = f.locator('.rc-imageselect').count() > 0
            has_dos = f.locator('.rc-doscaptcha-header-text').count() > 0
            print(f"Frame {idx}: audio={has_audio}, vis={has_vis}, dos={has_dos}")
            if has_audio:
                btn = f.locator('#recaptcha-audio-button')
                print("  Audio visible:", btn.is_visible())
                btn.click()
                time.sleep(2)
                print("  After click, doscaptcha:", f.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message').count() > 0)
                print("  Download link count:", f.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")').count())
    b.close()
