import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-web-security'
        ]
    )
    ctx = b.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 800}
    )
    pg = ctx.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)
    
    anchors = pg.locator('iframe[src*="recaptcha/api2/anchor"]').all()
    print("Found anchors with patchright:", len(anchors), flush=True)
    for idx, a in enumerate(anchors):
        box = a.bounding_box()
        if box and box['y'] > 1000:
            chk = a.content_frame.locator('#recaptcha-anchor')
            chk.click()
            print("Clicked anchor!", flush=True)
            break
            
    time.sleep(2)
    for f in pg.frames:
        if 'bframe' in f.url:
            print("Found bframe!", flush=True)
            audio_btn = f.locator('#recaptcha-audio-button')
            if audio_btn.is_visible():
                print("Clicking audio button...", flush=True)
                audio_btn.click()
                time.sleep(2)
                is_dos = f.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message').count() > 0
                dl = f.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
                print(f"Audio Challenge Result: doscaptcha={is_dos}, download_count={dl.count()}", flush=True)
                if dl.count() > 0:
                    href = dl.first.get_attribute('href')
                    print(f"🎉 Audio link: {href}", flush=True)
    b.close()
