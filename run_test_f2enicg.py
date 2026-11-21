import sys
import os
import time
import io
import re
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot')
from captcha_ai_solver import CaptchaAISolver
from playwright.sync_api import sync_playwright

MODEL_PATH = r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot\yolov8n.onnx'
solver = CaptchaAISolver(MODEL_PATH)

def bypass_url(target_url):
    print("=" * 60)
    print(" 🚀 UNIVERSAL LINK4M BYPASS (ZERO-PASS + YOLOV8)")
    print(f" Target: {target_url}")
    print("=" * 60)

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

        def handle_response(resp):
            nonlocal destination_url
            if any(k in resp.url for k in ['check-captcha', 'get-link-info']):
                try:
                    data = resp.json()
                    print(f"\n[API {resp.url.split('/')[-1]}] Status: {resp.status}, Body:", data)
                    if data.get('url'):
                        destination_url = data['url']
                        print("\n" + "=" * 60)
                        print("🎉 DESTINATION UNLOCKED:", destination_url)
                        print("=" * 60)
                except Exception:
                    pass

        page.on('response', handle_response)

        # Bypass sponsor mission completely
        page.route('**/api/campaign/get-advertise', lambda r: r.abort())

        print("[1] Loading page with zero-pass fallback...")
        page.goto(target_url, wait_until='networkidle')
        time.sleep(2)

        # Click checkbox
        recaptcha_el = page.wait_for_selector('#recaptcha iframe', timeout=15000)
        anchor_frame = recaptcha_el.content_frame()
        print("[2] Clicking reCAPTCHA anchor...")
        anchor_frame.wait_for_selector('#recaptcha-anchor', timeout=10000).click()

        # Monitor reCAPTCHA status
        active_bframe = None
        for attempt in range(1, 25):
            time.sleep(1)
            if anchor_frame.query_selector('.recaptcha-checkbox-checked') or destination_url:
                print("[✓] reCAPTCHA green tick verified!")
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
                print(f"[3] Challenge detected (Attempt {attempt})!")
                break

        if active_bframe:
            for round_idx in range(1, 6):
                time.sleep(1.5)
                if anchor_frame.query_selector('.recaptcha-checkbox-checked') or destination_url:
                    print("[✓] Challenge passed!")
                    break

                prompt_el = active_bframe.query_selector('.rc-imageselect-desc-wrapper, .rc-imageselect-desc')
                if not prompt_el or not prompt_el.is_visible():
                    print("Waiting for next prompt...")
                    time.sleep(1)
                    continue

                prompt_text = prompt_el.inner_text().strip()
                print(f"\n--- [Round {round_idx}] Prompt: {repr(prompt_text)} ---")

                target_strong = prompt_el.query_selector('strong')
                target_name = target_strong.inner_text().strip() if target_strong else prompt_text
                print(f"Target object: '{target_name}'")

                # Find table
                table = active_bframe.query_selector('table.rc-imageselect-table-44, table.rc-imageselect-table-33')
                if not table:
                    time.sleep(1)
                    continue

                class_attr = table.get_attribute('class') or ''
                grid_size = 4 if '44' in class_attr else 3
                print(f"Grid: {grid_size}x{grid_size}")

                if grid_size == 3:
                    # Dynamic fading loop
                    for sub_turn in range(6):
                        table_img_bytes = table.screenshot()
                        img = Image.open(io.BytesIO(table_img_bytes)).convert('RGB')
                        solve_res = solver.solve_grid(img, target_name=target_name, grid_size=3, conf_thresh=0.15)
                        tiles = solve_res['tiles_to_click']
                        print(f"  [Turn {sub_turn+1}] Detections: {solve_res['detected_count']}, Tiles: {tiles}")

                        if not tiles:
                            print("  [✓] No more target objects on 3x3 grid!")
                            break

                        tile_elements = active_bframe.query_selector_all('td.rc-imageselect-tile')
                        for t_idx in tiles:
                            if t_idx < len(tile_elements):
                                tile_elements[t_idx].click()
                                time.sleep(0.4)

                        print("  Waiting 3.5s for replacement tile animations...")
                        time.sleep(3.5)
                else:
                    # 4x4 static grid
                    table_img_bytes = table.screenshot()
                    img = Image.open(io.BytesIO(table_img_bytes)).convert('RGB')
                    solve_res = solver.solve_grid(img, target_name=target_name, grid_size=4, conf_thresh=0.18)
                    tiles = solve_res['tiles_to_click']
                    print(f"4x4 Detections: {solve_res['detected_count']}, Tiles: {tiles}")

                    tile_elements = active_bframe.query_selector_all('td.rc-imageselect-tile')
                    for t_idx in tiles:
                        if t_idx < len(tile_elements):
                            tile_elements[t_idx].click()
                            time.sleep(0.3)

                time.sleep(1)
                verify_btn = active_bframe.query_selector('#recaptcha-verify-button')
                if verify_btn and verify_btn.is_visible():
                    print(f"Clicking #{verify_btn.get_attribute('id')} ('{verify_btn.inner_text()}')...")
                    verify_btn.click()
                    time.sleep(2)

        # Check get link button
        print("\n[4] Waiting for destination link...")
        for _ in range(15):
            if destination_url:
                break
            btn = page.query_selector('a.get-link:not(.disabled)')
            if btn:
                print("[✓] Clicking 'Get Link' button...")
                btn.click()
                time.sleep(2)
            time.sleep(1)

        time.sleep(2)
        browser.close()
        return destination_url

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'https://link4m.org/go/F2EnICG'
    url = bypass_url(target)
    if url:
        print(f"\n🏆 UNLOCKED DESTINATION: {url}")
    else:
        print("\n[!] Failed to unlock destination.")
