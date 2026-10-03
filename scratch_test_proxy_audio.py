import sys, os, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

sys.path.insert(0, r'c:\Users\XUAN\.gemini\antigravity\scratch\Link4M_Bypass_Suite\src\core')
from config import load_proxies

proxies = load_proxies()
print(f"Loaded {len(proxies)} authenticated residential proxies.")

for p_cfg in proxies[:5]:
    server = p_cfg['server']
    print(f"\n--- Testing proxy: {server} ---")
    try:
        with sync_playwright() as p:
            proxy_args = {
                "server": p_cfg["server"],
                "username": p_cfg["username"],
                "password": p_cfg["password"]
            }
            b = p.chromium.launch(headless=True, proxy=proxy_args)
            ctx = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
            pg = ctx.new_page()
            
            # Check public ip
            try:
                pg.goto('https://api.ipify.org?format=json', timeout=8000)
                print("  Public IP via proxy:", pg.inner_text("body"))
            except Exception as e:
                print("  Proxy connection timeout/error:", e)
                b.close()
                continue
                
            # Navigate to link4m
            pg.goto('https://link4m.net/go/2kCcIqn', timeout=15000)
            pg.wait_for_timeout(3000)
            
            # Click recaptcha anchor
            anchors = pg.locator('iframe[src*="recaptcha/api2/anchor"]').all()
            for a in anchors:
                box = a.bounding_box()
                if box and box['y'] > 1000:
                    a.content_frame.locator('#recaptcha-anchor').click()
                    print("  Clicked anchor at y=", box['y'])
                    break
                    
            time.sleep(2)
            for f in pg.frames:
                if 'bframe' in f.url:
                    has_audio = f.locator('#recaptcha-audio-button').count() > 0
                    print("  bframe found, audio button visible:", has_audio)
                    if has_audio:
                        f.locator('#recaptcha-audio-button').click()
                        time.sleep(2)
                        is_dos = f.locator('.rc-doscaptcha-header-text, .rc-audiochallenge-error-message').count() > 0
                        dl = f.locator('.rc-audiochallenge-tdownload-link, a:has-text("Download")')
                        print(f"  Result with proxy {server}: doscaptcha={is_dos}, download_count={dl.count()}")
                        if dl.count() > 0:
                            print(f"  🎉 SUCCESS! Audio download URL: {dl.first.get_attribute('href')}")
                            b.close()
                            sys.exit(0)
            b.close()
    except Exception as ex:
        print(f"  Proxy test exception: {ex}")
