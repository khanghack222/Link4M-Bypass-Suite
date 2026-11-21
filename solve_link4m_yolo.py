import sys
import os
import time
import io
from PIL import Image
import requests

sys.stdout.reconfigure(encoding='utf-8')

# Ensure python311 packages
sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot')
from captcha_ai_solver import CaptchaAISolver
from playwright.sync_api import sync_playwright

MODEL_PATH = r'C:\Users\XUAN\.gemini\antigravity\scratch\Discord_Bypass_Bot\yolov8n.onnx'
solver = CaptchaAISolver(MODEL_PATH)

def solve_link4m(alias="68pw167Y", code="LbxReE"):
    print(f"==================================================")
    print(f" 🚀 LINK4M BYPASS WITH YOLOV8 RECAPTCHA SOLVER")
    print(f" Target Alias: {alias}")
    print(f" Sponsor Code: {code}")
    print(f"==================================================")

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

        destination_url = None

        def handle_response(resp):
            nonlocal destination_url
            if 'get-link-info' in resp.url:
                try:
                    data = resp.json()
                    print(f"[get-link-info API] Status: {resp.status}, Body: {data}")
                    if data.get('url'):
                        destination_url = data['url']
                        print("==================================================")
                        print("🎉 FINAL DESTINATION UNLOCKED:", destination_url)
                        print("==================================================")
                        with open(r'C:\Users\XUAN\.gemini\antigravity\scratch\Link4M_Bypass_Suite\final_destination.txt', 'w', encoding='utf-8') as f:
                            f.write(destination_url)
                except Exception:
                    pass

        page.on('response', handle_response)

        print("[1] Loading page https://link4m.net/go/" + alias)
        page.goto(f'https://link4m.net/go/{alias}', wait_until='networkidle')

        print("[2] Waiting for password input...")
        page.wait_for_selector('input.password', timeout=20000)
        page.fill('input.password', code)
        page.dispatch_event('input.password', 'input')
        print(f"[✓] Filled code: {code}")

        time.sleep(2)

        # Find anchor iframe
        print("[3] Clicking reCAPTCHA checkbox...")
        anchor_frame = None
        for frame in page.frames:
            if 'recaptcha/api2/anchor' in frame.url:
                anchor_frame = frame
                break

        if not anchor_frame:
            print("[!] Anchor frame not found")
            return

        anchor_frame.click('#recaptcha-anchor', force=True)
        print("[✓] Clicked reCAPTCHA checkbox")

        time.sleep(3)

        # Check if anchor is already checked (green checkmark)
        is_checked = anchor_frame.is_visible('.recaptcha-checkbox-checked')
        if is_checked:
            print("[✓] reCAPTCHA passed automatically without visual challenge!")
        else:
            print("[4] Visual Challenge detected! Searching for bframe...")
            bframe = None
            for _ in range(10):
                for frame in page.frames:
                    if 'recaptcha/api2/bframe' in frame.url:
                        bframe = frame
                        break
                if bframe:
                    break
                time.sleep(1)

            if not bframe:
                print("[!] bframe not found")
            else:
                print(f"[✓] Found bframe: {bframe.url[:70]}...")
                
                # Visual solve loop
                for round_num in range(1, 6):
                    print(f"\n--- Challenge Round {round_num} ---")
                    time.sleep(2)

                    # Check if solved
                    if anchor_frame.is_visible('.recaptcha-checkbox-checked'):
                        print("[✓] reCAPTCHA solved successfully!")
                        break

                    # Extract target name using multiple resilient selectors
                    target_name = None
                    selectors = [
                        '.rc-imageselect-desc-wrapper strong',
                        '.rc-imageselect-desc-no-canonical strong',
                        '.rc-imageselect-instructions strong',
                        '.rc-imageselect-desc strong',
                        '.rc-imageselect-desc-wrapper b',
                        '#rc-imageselect strong'
                    ]
                    for sel in selectors:
                        elem = bframe.query_selector(sel)
                        if elem and elem.is_visible():
                            target_name = elem.inner_text().strip()
                            break

                    if not target_name:
                        # Fallback: inspect full desc text
                        desc_elem = bframe.query_selector('.rc-imageselect-desc-wrapper, .rc-imageselect-instructions')
                        if desc_elem:
                            text = desc_elem.inner_text().lower()
                            for k in ['bus', 'car', 'motorcycle', 'bicycle', 'traffic light', 'fire hydrant', 'boat', 'xe máy', 'ô tô', 'xe buýt', 'xe đạp', 'đèn giao thông', 'vòi cứu hỏa']:
                                if k in text:
                                    target_name = k
                                    break

                    if not target_name:
                        print("[!] Cannot find target name, defaulting to 'car'")
                        target_name = "car"

                    print(f"Target Object: '{target_name}'")

                    # Check grid size (3x3 or 4x4)
                    table = None
                    for t_sel in ['.rc-imageselect-table-44', '.rc-imageselect-table-33', '#rc-imageselect-target', '.rc-imageselect-challenge']:
                        t = bframe.query_selector(t_sel)
                        if t and t.is_visible():
                            table = t
                            break

                    if not table:
                        print("[!] Table not found directly, waiting for table selector...")
                        table = bframe.wait_for_selector('.rc-imageselect-table-44, .rc-imageselect-table-33, #rc-imageselect-target', timeout=6000)

                    class_attr = table.get_attribute('class') or ''
                    grid_size = 4 if '44' in class_attr else 3
                    print(f"Grid Size: {grid_size}x{grid_size}")

                    # Handle 3x3 dynamic fading tiles vs 4x4 static grid
                    is_dynamic = (grid_size == 3)
                    
                    if is_dynamic:
                        print("Dynamic 3x3 Challenge detected: Clicking fading tiles until none left...")
                        for sub_turn in range(6):
                            # Screenshot table
                            table_img_bytes = table.screenshot()
                            img = Image.open(io.BytesIO(table_img_bytes)).convert('RGB')
                            solve_res = solver.solve_grid(img, target_name=target_name, grid_size=3, conf_thresh=0.15)
                            tiles = solve_res['tiles_to_click']
                            print(f"  [Turn {sub_turn+1}] Detections: {solve_res['detected_count']}, Tiles: {tiles}")
                            
                            if not tiles:
                                print("  [✓] No more target objects detected on 3x3 grid!")
                                break

                            tile_elements = bframe.query_selector_all('td.rc-imageselect-tile')
                            for t_idx in tiles:
                                if t_idx < len(tile_elements):
                                    print(f"    -> Clicking tile #{t_idx}...")
                                    tile_elements[t_idx].click()
                                    time.sleep(0.5)

                            print("    Waiting 3.5s for replacement tile animations...")
                            time.sleep(3.5)
                    else:
                        # 4x4 static grid
                        table_img_bytes = table.screenshot()
                        img = Image.open(io.BytesIO(table_img_bytes)).convert('RGB')
                        solve_res = solver.solve_grid(img, target_name=target_name, grid_size=4, conf_thresh=0.18)
                        tiles = solve_res['tiles_to_click']
                        print(f"4x4 Detections: {solve_res['detected_count']}, Tiles: {tiles}")
                        
                        tile_elements = bframe.query_selector_all('td.rc-imageselect-tile')
                        for t_idx in tiles:
                            if t_idx < len(tile_elements):
                                print(f"  -> Clicking tile #{t_idx}...")
                                tile_elements[t_idx].click()
                                time.sleep(0.4)

                    time.sleep(1)

                    # Click verify/next button
                    verify_btn = bframe.query_selector('#recaptcha-verify-button')
                    if verify_btn:
                        btn_text = verify_btn.inner_text()
                        print(f"Clicking #{verify_btn.get_attribute('id')} ('{btn_text}')...")
                        verify_btn.click()
                        time.sleep(2)

        # Check get-link button
        print("\n[5] Checking 'Get Link' button...")
        for _ in range(15):
            time.sleep(2)
            if destination_url:
                break
            get_btn = page.query_selector('a.get-link:not(.disabled)')
            if get_btn:
                print("[✓] 'Get Link' button is ACTIVE! Clicking...")
                get_btn.click()
                time.sleep(3)

        if destination_url:
            print("\n==================================================")
            print("🎉 VICTORY! FINAL UNLOCKED LINK:")
            print(destination_url)
            print("==================================================")
        else:
            print("[!] Could not unlock link within timeout.")

        time.sleep(3)
        browser.close()

if __name__ == '__main__':
    solve_link4m()
