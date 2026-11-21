import sys
import os
import time
import io
import re
from PIL import Image
import requests

sys.stdout.reconfigure(encoding='utf-8')

# Ensure imports
sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot')
from captcha_ai_solver import CaptchaAISolver
from playwright.sync_api import sync_playwright

MODEL_PATH = r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot\yolov8n.onnx'
solver = CaptchaAISolver(MODEL_PATH)

def bypass_link4m(target_url):
    print("=" * 60)
    print(" 🚀 UNIVERSAL LINK4M BYPASS ENGINE (YOLOv8 + ZERO-PASS)")
    print(f" Target: {target_url}")
    print("=" * 60)

    # Extract alias
    m = re.search(r'/go/([a-zA-Z0-9_-]+)', target_url)
    alias = m.group(1) if m else "F2EnICG"

    destination_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 850}
        )
        page = context.new_page()

        # Listen to API responses
        def handle_response(resp):
            nonlocal destination_url
            if any(k in resp.url for k in ['check-captcha', 'get-link-info']):
                try:
                    data = resp.json()
                    print(f"[{resp.url.split('/')[-1]}] Response:", data)
                    if data.get('url'):
                        destination_url = data['url']
                        print("\n" + "=" * 60)
                        print("🎉 DESTINATION UNLOCKED:", destination_url)
                        print("=" * 60)
                except Exception:
                    pass

        page.on('response', handle_response)

        # ZERO-PASS EXPLOIT: Abort campaign advertising to force fallback to clean reCAPTCHA
        page.route('**/api/campaign/get-advertise', lambda route: route.abort())

        print(f"[1] Navigating to {target_url} (Sponsor mission bypassed)...")
        page.goto(target_url, wait_until='networkidle')
        time.sleep(2)

        # Find reCAPTCHA anchor iframe directly inside #recaptcha
        print("[2] Locating active reCAPTCHA anchor...")
        anchor_frame = None
        for _ in range(10):
            recaptcha_el = page.query_selector('#recaptcha iframe')
            if recaptcha_el:
                anchor_frame = recaptcha_el.content_frame()
                if anchor_frame:
                    break
            time.sleep(1)

        if not anchor_frame:
            print("[!] Visible anchor frame not found!")
            browser.close()
            return None

        # Click the checkbox
        print("[3] Clicking reCAPTCHA checkbox...")
        checkbox = anchor_frame.wait_for_selector('#recaptcha-anchor', timeout=10000)
        checkbox.click()
        time.sleep(2)

        # Check if ticked immediately
        checked = anchor_frame.query_selector('.recaptcha-checkbox-checked')
        if checked:
            print("[✓] reCAPTCHA passed without image challenge (1-click green tick)!")
        else:
            print("[4] reCAPTCHA challenge opened! Locating active bframe...")
            bframe = None
            for _ in range(15):
                for f in page.frames:
                    if 'recaptcha/api2/bframe' in f.url:
                        if f.query_selector('.rc-imageselect-desc-wrapper, .rc-imageselect-desc'):
                            bframe = f
                            break
                if bframe:
                    break
                time.sleep(0.5)

            if not bframe:
                print("[!] Bframe not found!")
            else:
                # Solve challenge rounds
                for round_num in range(1, 6):
                    time.sleep(1.5)
                    # Check if already solved
                    if anchor_frame.query_selector('.recaptcha-checkbox-checked') or destination_url:
                        print("[✓] reCAPTCHA successfully validated!")
                        break

                    # Get prompt instruction
                    prompt_el = bframe.query_selector('.rc-imageselect-desc-wrapper, .rc-imageselect-desc')
                    if not prompt_el:
                        print("No prompt found, checking if finished...")
                        time.sleep(1)
                        if anchor_frame.query_selector('.recaptcha-checkbox-checked'):
                            break
                        continue

                    prompt_text = prompt_el.inner_text().strip()
                    print(f"\n--- [Round {round_num}] Prompt: {repr(prompt_text)} ---")

                    # Extract target
                    target_strong = prompt_el.query_selector('strong')
                    target_name = target_strong.inner_text().strip() if target_strong else prompt_text
                    print(f"Target object: '{target_name}'")

                    # Check grid mode (3x3 vs 4x4)
                    table_3x3 = bframe.query_selector('table.rc-imageselect-table-33')
                    table_4x4 = bframe.query_selector('table.rc-imageselect-table-44')

                    if table_4x4:
                        print("Grid Type: 4x4 (16 tiles)")
                        payload_img = bframe.query_selector('.rc-image-tile-44')
                        if not payload_img:
                            continue
                        img_bytes = payload_img.screenshot()
                        image = Image.open(io.BytesIO(img_bytes))

                        results = solver.solve_grid(image, target_name, grid_size=4)
                        tiles_to_click = results.get('tiles_to_click', []) if isinstance(results, dict) else results
                        print("AI selected 4x4 tiles:", tiles_to_click)

                        tiles = bframe.query_selector_all('td.rc-imageselect-tile')
                        for idx in tiles_to_click:
                            if idx < len(tiles):
                                tiles[idx].click()
                                time.sleep(0.2)
                    else:
                        print("Grid Type: 3x3 (9 tiles)")
                        # Handle dynamic fading or static 3x3
                        payload_img = bframe.query_selector('.rc-image-tile-33, .rc-imageselect-payload img')
                        if payload_img:
                            img_bytes = payload_img.screenshot()
                            image = Image.open(io.BytesIO(img_bytes))
                            results = solver.solve_grid(image, target_name, grid_size=3)
                            tiles_to_click = results.get('tiles_to_click', []) if isinstance(results, dict) else results
                            print("AI selected 3x3 tiles:", tiles_to_click)

                            tiles = bframe.query_selector_all('td.rc-imageselect-tile')
                            for idx in tiles_to_click:
                                if idx < len(tiles):
                                    tiles[idx].click()
                                    time.sleep(0.3)

                    # Click verify/next button
                    time.sleep(1)
                    verify_btn = bframe.query_selector('#recaptcha-verify-button')
                    if verify_btn:
                        btn_name = verify_btn.inner_text()
                        print(f"Clicking #{verify_btn.get_attribute('id')} ('{btn_name}')...")
                        verify_btn.click()
                        time.sleep(2)

        # Check get-link button
        print("\n[5] Verifying destination link...")
        for _ in range(10):
            if destination_url:
                break
            get_btn = page.query_selector('a.get-link:not(.disabled)')
            if get_btn:
                print("[✓] 'Get Link' button activated! Clicking...")
                get_btn.click()
                time.sleep(2)
            time.sleep(1)

        browser.close()
        return destination_url

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'https://link4m.org/go/F2EnICG'
    final = bypass_link4m(target)
    if final:
        print(f"\n==================================================")
        print(f"🏆 SUCCESS: {final}")
        print(f"==================================================")
    else:
        print("\n[!] Bypass completed without extracting destination URL.")
