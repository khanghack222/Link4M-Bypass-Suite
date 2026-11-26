import sys
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://link4m.net/go/68pw167Y', timeout=20000)
    page.wait_for_timeout(3500)
    
    anchors = page.locator('iframe[src*="recaptcha/api2/anchor"]').all()
    anchors[0].content_frame.locator('#recaptcha-anchor').click(force=True)
    time.sleep(2)
    
    for bf_loc in page.locator('iframe[src*="recaptcha/api2/bframe"]').all():
        bf = bf_loc.content_frame
        btn = bf.locator('#recaptcha-audio-button')
        if btn.count() > 0 and btn.is_visible():
            print('Found visible audio button locator!')
            box = btn.bounding_box()
            print('Audio button bounding box in page:', box)
            if box:
                page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                print('Clicked via page.mouse.click()!')
                time.sleep(2)
                for f in page.frames:
                    if 'bframe' in f.url:
                        text = f.evaluate('() => document.body ? document.body.innerText.substring(0, 250) : ""')
                        print('BFrame text after mouse click:', repr(text))
                        break
    b.close()
