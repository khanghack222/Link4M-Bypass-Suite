import os
import sys
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "core")
sys.path.insert(0, CORE_DIR)

from patchright.sync_api import sync_playwright
from config import CHROME_PATH, STEALTH_INIT_SCRIPT

target_url = "https://link4m.net/go/68pw167Y"

print("="*60)
print("⚡ KIỂM THỬ GIẢI PHÁP RECAPTCHA BỀN VỮNG: WARMED PROFILE ⚡")
print("="*60, flush=True)

# Copy profile or use dedicated warmed profile directory
profile_dir = os.path.abspath(r"data\temp\warmed_chrome_profile")
os.makedirs(profile_dir, exist_ok=True)

with sync_playwright() as p:
    args = [
        "--no-sandbox",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--window-size=1280,720",
        "--mute-audio=false",
        "--ignore-certificate-errors"
    ]
    
    print("[*] Launching browser with Persistent Profile...", flush=True)
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        executable_path=CHROME_PATH if CHROME_PATH and os.path.exists(CHROME_PATH) else None,
        headless=True,
        args=args,
        viewport={"width": 1280, "height": 720}
    )
    context.add_init_script(STEALTH_INIT_SCRIPT)
    page = context.pages[0] if context.pages else context.new_page()
    
    print(f"[*] Navigating to {target_url}...", flush=True)
    t0 = time.perf_counter()
    page.goto(target_url, timeout=20000)
    page.wait_for_timeout(3000)
    
    # 1. Tìm anchor
    anchors = page.locator('iframe[src*="recaptcha/api2/anchor"]').all()
    print(f"[*] Found {len(anchors)} reCAPTCHA anchors.", flush=True)
    
    for idx, a in enumerate(anchors):
        box = a.bounding_box()
        cf = a.content_frame
        if not cf:
            continue
        chk = cf.locator('#recaptcha-anchor')
        if chk.count() == 0:
            continue
            
        print(f"[*] Clicking reCAPTCHA anchor {idx}...", flush=True)
        # Move mouse realistically
        if box:
            page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=10)
        time.sleep(0.2)
        chk.click(force=True)
        time.sleep(2.0)
        
        status = chk.get_attribute("aria-checked")
        print(f"[+] Anchor {idx} checked status: {status}", flush=True)
        if status == "true":
            token = page.evaluate("() => { for (const el of document.querySelectorAll('[name=\"g-recaptcha-response\"]')) { if (el.value && el.value.length > 20) return el.value; } return ''; }")
            elapsed = round((time.perf_counter() - t0), 2)
            print(f"🎉 INSTANT SOLVED IN {elapsed}s! Token length: {len(token)}", flush=True)
            print(f"Token: {token[:60]}...", flush=True)
            break
        else:
            print("[-] Required challenge. Testing Direct JS Audio Solver...", flush=True)
            # Find bframe
            for f in page.frames:
                if 'bframe' in f.url and f.locator('#recaptcha-audio-button').count() > 0:
                    clicked = f.evaluate("() => { const b = document.querySelector('#recaptcha-audio-button'); if(b) { b.click(); return true; } return false; }")
                    print(f"  [+] Clicked audio button: {clicked}", flush=True)
                    time.sleep(1.5)
                    text = f.evaluate("() => document.body ? document.body.innerText.substring(0, 150) : ''")
                    print(f"  [*] Challenge text: {repr(text)}", flush=True)
                    break
                    
    context.close()
