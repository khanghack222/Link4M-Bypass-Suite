import time
from playwright.sync_api import sync_playwright
import sys, os
sys.path.insert(0, r'c:\Users\XUAN\.gemini\antigravity\scratch\Link4M_Bypass_Suite\src\core')
from recaptcha_solver import get_solver_instance

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)
    
    # Check visual solver directly
    solver = get_solver_instance(headless=True)
    print("Testing direct visual solver on Link4M...", flush=True)
    
    # We test solve_on_page but without clicking audio button
    for a in pg.locator('iframe[src*="recaptcha/api2/anchor"]').all():
        box = a.bounding_box()
        if box and box['y'] > 1000:
            chk = a.content_frame.locator('#recaptcha-anchor')
            chk.click()
            print("Clicked anchor!", flush=True)
            time.sleep(2)
            
            # Find bframe
            for f in pg.frames:
                if 'bframe' in f.url:
                    print("Found bframe!")
                    has_vis = f.locator('.rc-imageselect-instructions, .rc-imageselect-desc, .rc-imageselect').count() > 0
                    print("Visual challenge visible:", has_vis)
                    if has_vis:
                        inst = f.locator('.rc-imageselect-instructions, .rc-imageselect-desc').first.inner_text().replace('\n', ' ')
                        print("Challenge instruction:", inst)
                        res = solver.solve_image_challenge(pg, f, chk, max_rounds=5)
                        print("Visual solve result:", res)
                        print("Anchor checked status:", chk.get_attribute('aria-checked'))
            break
    b.close()
