import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars"
        ]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        locale="en-US"
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.navigator.chrome = { runtime: {} };
    """)
    page = context.new_page()
    page.goto('https://google.com/recaptcha/api2/demo', wait_until='networkidle')
    time.sleep(1)

    a = page.locator('iframe[src*="recaptcha/api2/anchor"]').first
    a.content_frame.locator('#recaptcha-anchor').click(force=True)
    time.sleep(2)

    bname = 'c-' + a.get_attribute('name')[2:]
    bf = page.locator(f'iframe[name="{bname}"]').first.content_frame

    audio_btn = bf.locator('#recaptcha-audio-button')
    print('audio_btn count with clean context:', audio_btn.count())
    audio_btn.click(force=True)
    time.sleep(2)

    link = bf.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
    print('Download link count with clean context:', link.count())
    if link.count() > 0:
        print('AUDIO URL:', link.first.get_attribute('href')[:60])
    else:
        err = bf.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message')
        print('Error text:', err.inner_text() if err.count() > 0 else 'none')
    browser.close()
