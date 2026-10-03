import sys, os, time, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with open('live_proxy.json', 'r', encoding='utf-8') as f:
    p_cfg = json.load(f)

print(f"Using Live Proxy: {p_cfg['server']} (Exit IP: 31.59.20.176)", flush=True)

proxy_args = {
    "server": p_cfg["server"],
    "username": p_cfg["username"],
    "password": p_cfg["password"]
}

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, proxy=proxy_args)
    ctx = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    pg = ctx.new_page()

    try:
        print("Navigating to https://link4m.net/go/2kCcIqn via Proxy...", flush=True)
        resp = pg.goto('https://link4m.net/go/2kCcIqn', timeout=35000, wait_until="domcontentloaded")
        print("Page response status:", resp.status if resp else "None", flush=True)
        pg.wait_for_timeout(4000)

        # Click reCAPTCHA anchor
        anchors = pg.locator('iframe[src*="recaptcha/api2/anchor"]').all()
        print(f"Found {len(anchors)} anchors.", flush=True)
        for a in anchors:
            box = a.bounding_box()
            if box and box['y'] > 1000:
                a.content_frame.locator('#recaptcha-anchor').click()
                print("Clicked anchor at y=", box['y'], flush=True)
                break
    except Exception as e:
        import traceback
        traceback.print_exc()

    time.sleep(2.5)

    for f in pg.frames:
        if 'bframe' in f.url:
            print("Found bframe!", flush=True)
            btn = f.locator('#recaptcha-audio-button')
            if btn.is_visible():
                print("Clicking #recaptcha-audio-button via Proxy...", flush=True)
                btn.click()
                time.sleep(2)
                is_dos = f.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message').count() > 0
                dl = f.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
                print(f"Proxy Result: doscaptcha={is_dos}, download_link_count={dl.count()}", flush=True)
                if dl.count() > 0:
                    href = dl.first.get_attribute('href')
                    print(f"\n🎉🎉🎉 SUCCESS! AUDIO CHALLENGE UNLOCKED! 🎉🎉🎉\nAudio URL: {href}", flush=True)
                    
                    # Transcribe with faster-whisper
                    import urllib.request, tempfile, re
                    import faster_whisper
                    tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                    urllib.request.urlretrieve(href, tmp.name)
                    model = faster_whisper.WhisperModel('tiny.en', device='cpu', compute_type='int8')
                    segments, _ = model.transcribe(tmp.name, language='en')
                    ans = "".join(s.text for s in segments).strip().lower()
                    ans = re.sub(r'[^a-zA-Z0-9\s]', '', ans)
                    print(f"🎉 TRANSCRIBED ANSWER: '{ans}'", flush=True)
                    
                    # Fill into input and verify
                    f.locator('#audio-response').fill(ans)
                    f.locator('#recaptcha-verify-button').click()
                    time.sleep(2)
                    
                    # Check token
                    tok = pg.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
                    print(f"🎉 SOLVED RECAPTCHA TOKEN: {tok[:60]}... (len={len(tok)})", flush=True)
    b.close()
