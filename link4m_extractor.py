import sys
import os
import time
import io
import re
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

# Ensure path to solver
sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot')
from captcha_ai_solver import CaptchaAISolver
from playwright.sync_api import sync_playwright

MODEL_PATH = r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot\yolov8n.onnx'

def extract_destination(target_url, headless=True):
    print("=" * 65)
    print(" 🚀 LINK4M DESTINATION EXTRACTOR (ZERO-PASS + YOLOV8 ONNX)")
    print(f" Target URL: {target_url}")
    print("=" * 65)

    solver = CaptchaAISolver(MODEL_PATH)
    destination_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-infobars'
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 850}
        )
        page = context.new_page()

        # Evasion: remove navigator.webdriver
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Network interceptor to capture the destination response
        def handle_response(resp):
            nonlocal destination_url
            if any(endpoint in resp.url for endpoint in ['check-captcha', 'get-link-info']):
                try:
                    data = resp.json()
                    print(f"[{resp.url.split('/')[-1]}] Response Status: {resp.status}")
                    if data.get('url'):
                        destination_url = data['url']
                        print("\n" + "=" * 65)
                        print("🎉 DESTINATION URL INTERCEPTED:", destination_url)
                        print("=" * 65)
                except Exception:
                    pass

        page.on('response', handle_response)

        # Fallback exploit: abort advertising request to skip sponsor mission
        page.route('**/api/campaign/get-advertise', lambda r: r.abort())

        print("[1] Loading page with zero-pass fallback...")
        page.goto(target_url, wait_until='networkidle')
        time.sleep(2)

        # Locate visible recaptcha iframe
        print("[2] Locating active reCAPTCHA...")
        recaptcha_el = page.wait_for_selector('#recaptcha iframe', timeout=15000)
        anchor_frame = recaptcha_el.content_frame()
        if not anchor_frame:
            print("[!] Could not access anchor frame!")
            browser.close()
            return None

        # Click anchor
        print("[3] Clicking reCAPTCHA anchor...")
        anchor_frame.wait_for_selector('#recaptcha-anchor', timeout=10000).click()

        # Check if solved immediately or challenge appears
        active_bframe = None
        for attempt in range(1, 20):
            time.sleep(1)
            if anchor_frame.query_selector('.recaptcha-checkbox-checked') or destination_url:
                print("[✓] reCAPTCHA passed directly (green checkmark)!")
                break

            for f in page.frames:
                if 'bframe' in f.url:
                    try:
                        desc = f.query_selector('.rc-imageselect-desc-wrapper, .rc-imageselect-desc')
                        if desc and desc.is_visible():
                            active_bframe = f
                            break
                    except Exception:
                        pass

            if active_bframe:
                print(f"[4] Challenge dialog active (Detected in attempt {attempt})!")
                break

        # Solve challenge rounds with YOLOv8
        if active_bframe:
            for round_idx in range(1, 16):
                time.sleep(1.5)
                if anchor_frame.query_selector('.recaptcha-checkbox-checked') or destination_url:
                    print("[✓] reCAPTCHA successfully completed!")
                    break

                prompt_el = active_bframe.query_selector('.rc-imageselect-desc-wrapper, .rc-imageselect-desc')
                if not prompt_el or not prompt_el.is_visible():
                    time.sleep(1)
                    if anchor_frame.query_selector('.recaptcha-checkbox-checked') or destination_url:
                        break
                    continue

                prompt_text = prompt_el.inner_text().strip()
                print(f"\n--- [Round {round_idx}] Prompt: {repr(prompt_text)} ---")

                target_strong = prompt_el.query_selector('strong')
                target_name = target_strong.inner_text().strip() if target_strong else prompt_text
                print(f"Target Object: '{target_name}'")

                # Find the currently VISIBLE table
                table = None
                for tbl in active_bframe.query_selector_all('table.rc-imageselect-table-33, table.rc-imageselect-table-44'):
                    if tbl.is_visible():
                        table = tbl
                        break

                if not table:
                    time.sleep(1)
                    continue

                class_attr = table.get_attribute('class') or ''
                grid_size = 4 if '44' in class_attr else 3
                print(f"Grid Layout: {grid_size}x{grid_size}")

                if grid_size == 3:
                    # Dynamic fading tile resolution
                    for sub_turn in range(6):
                        table_img_bytes = table.screenshot()
                        img = Image.open(io.BytesIO(table_img_bytes)).convert('RGB')
                        
                        # YOLOv8 inference with low threshold for small objects
                        res = solver.solve_grid(img, target_name=target_name, grid_size=3, conf_thresh=0.15)
                        tiles_to_click = res.get('tiles_to_click', [])
                        print(f"  [Turn {sub_turn+1}] Detections: {res['detected_count']}, Tiles to click: {tiles_to_click}")

                        if not tiles_to_click:
                            print("  [✓] All target objects cleared from 3x3 grid!")
                            break

                        tile_elements = table.query_selector_all('td.rc-imageselect-tile')
                        for t_idx in tiles_to_click:
                            if t_idx < len(tile_elements):
                                print(f"    -> Clicking tile #{t_idx}...")
                                tile_elements[t_idx].click()
                                time.sleep(0.3)

                        print("    Waiting 3.8s for replacement tile animations...")
                        time.sleep(3.8)
                else:
                    # Static 4x4 resolution
                    table_img_bytes = table.screenshot()
                    img = Image.open(io.BytesIO(table_img_bytes)).convert('RGB')
                    res = solver.solve_grid(img, target_name=target_name, grid_size=4, conf_thresh=0.18)
                    tiles_to_click = res.get('tiles_to_click', [])
                    print(f"4x4 Detections: {res['detected_count']}, Tiles to click: {tiles_to_click}")

                    tile_elements = table.query_selector_all('td.rc-imageselect-tile')
                    for t_idx in tiles_to_click:
                        if t_idx < len(tile_elements):
                            tile_elements[t_idx].click()
                            time.sleep(0.2)

                time.sleep(1)
                verify_btn = active_bframe.query_selector('#recaptcha-verify-button')
                if verify_btn and verify_btn.is_visible():
                    print(f"Clicking #{verify_btn.get_attribute('id')} ('{verify_btn.inner_text()}')...")
                    verify_btn.click()
                    time.sleep(2.5)

        # Retrieve destination
        print("\n[5] Waiting for final destination resolution...")
        for _ in range(15):
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
    result = extract_destination(target, headless=False)
    if result:
        print("\n" + "=" * 65)
        print("🏆 FINAL DESTINATION URL:")
        print(result)
        print("=" * 65)
        with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination.txt', 'w', encoding='utf-8') as f:
            f.write(result)
    else:
        print("\n[!] Could not extract destination URL.")
