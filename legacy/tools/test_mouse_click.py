import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://google.com/recaptcha/api2/demo')
    a = page.locator('iframe[src*="recaptcha/api2/anchor"]').first
    box = a.bounding_box()
    print('Anchor center:', box['x'] + 28, box['y'] + 39)
    page.mouse.move(box['x'] + 28, box['y'] + 39)
    page.mouse.down()
    time.sleep(0.1)
    page.mouse.up()
    time.sleep(2)
    bname = 'c-' + a.get_attribute('name')[2:]
    bf = page.locator(f'iframe[name="{bname}"]').first.content_frame
    audio_btn = bf.locator('#recaptcha-audio-button')
    print('Audio button with mouse click:', audio_btn.count(), audio_btn.is_visible())
    if audio_btn.is_visible():
        abox = audio_btn.bounding_box()
        if abox:
            page.mouse.click(abox['x'] + 10, abox['y'] + 10)
            time.sleep(2)
            link = bf.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
            print('Download link with mouse click:', link.count())
    browser.close()
