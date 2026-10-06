import sys
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://link4m.net/go/68pw167Y', timeout=20000)
    page.wait_for_timeout(3500)
    
    anchors = page.locator('iframe[src*="recaptcha/api2/anchor"]').all()
    print('Total anchors found:', len(anchors))
    for i, a in enumerate(anchors):
        name = a.get_attribute('name')
        vis = a.is_visible()
        box = a.bounding_box()
        print(f'Anchor {i}: name={name}, visible={vis}, box={box}')
        cf = a.content_frame
        if cf:
            chk = cf.locator('#recaptcha-anchor')
            print(f'  chk count: {chk.count()}, checked={chk.get_attribute("aria-checked")}')
            try:
                chk.click(force=True)
                time.sleep(2)
                print(f'  after click checked={chk.get_attribute("aria-checked")}')
            except Exception as e:
                print(f'  click error: {e}')
            
    print('\nAll bframes now:')
    for f in page.frames:
        if 'bframe' in f.url:
            print(f' - BFrame: name={f.name}, url={f.url[:70]}')
            try:
                btns = f.evaluate('() => Array.from(document.querySelectorAll("button, .rc-button")).map(b => ({ id: b.id, class: b.className, text: b.innerText }))')
                print('   bframe buttons:', btns)
                h = f.evaluate('() => document.body ? document.body.innerText.substring(0, 200) : ""')
                print('   bframe text:', repr(h))
            except Exception as e:
                print('   eval error:', e)
    b.close()
