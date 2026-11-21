import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    # Run non-headless to ensure Cloudflare doesn't block what-on.com
    browser = p.chromium.launch(
        headless=False,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    page = context.new_page()

    # Log requests/responses
    def on_req(req):
        if 'what-on.com' in req.url:
            print(f'[REQ] {req.method} {req.url[:100]}')

    def on_resp(resp):
        if 'what-on.com' in resp.url and 'quest' in resp.url:
            try:
                print(f'[RESP CODE API] {resp.status} => {resp.text()}')
            except Exception as e:
                print(f'[RESP Error]: {e}')

    page.on('request', on_req)
    page.on('response', on_resp)

    # Init script to keep mouse_scroll active and tab visible
    page.add_init_script('''
        // Keep tab always visible
        Object.defineProperty(document, 'hidden', { get: () => false });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        window.addEventListener('blur', (e) => e.stopImmediatePropagation(), true);

        // Keep pageYOffset constantly changing so mouse_offset != tmp is always true
        let fakeScrollY = 500;
        Object.defineProperty(window, 'pageYOffset', {
            get: () => {
                fakeScrollY = (fakeScrollY + 13) % 20000 + 100;
                return fakeScrollY;
            }
        });

        // Continuously fire scroll events
        setInterval(() => {
            window.dispatchEvent(new Event('scroll'));
        }, 200);
    ''')

    print("[1] Navigating to https://soikeobongda.life ...")
    page.goto('https://soikeobongda.life', wait_until='domcontentloaded')
    time.sleep(3)

    # Wait for #BUQeFzS button
    print("[2] Waiting for button in #BUQeFzS...")
    page.wait_for_selector('#BUQeFzS button', timeout=15000)
    btn = page.query_selector('#BUQeFzS button')
    
    print("[3] Clicking button to initiate countdown...")
    btn.click()

    # Track countdown
    found_code = None
    for sec in range(95):
        time.sleep(1)

        try:
            status_text = page.eval_on_selector('.whatoncode', 'el => el.innerText').strip()
        except Exception:
            status_text = ""

        if sec % 5 == 0 or 'Mã' in status_text or 'Chưa' in status_text or 'Click' in status_text:
            print(f"  [{sec:02d}s] Countdown: {status_text.replace(chr(10), ' | ')}")

        # Check if step 1 completed and asked to click any link
        if 'click vào link bất kỳ' in status_text:
            print("[*] Step 1 finished! Clicking internal link for Step 2...")
            # Query valid internal navigation link
            link = page.query_selector('a[href*="/soi-keo-nha-cai/"], a[href*="/nha-cai-uy-tin/"], a[href*="/bong-da-anh/"]')
            if link:
                href = link.get_attribute('href')
                print(f"[*] Navigating to: {href}")
                link.click()
                page.wait_for_load_state('domcontentloaded')
                time.sleep(3)
                print("[*] On next page. Scrolling down to trigger/find Step 2...")
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(2)
                
                # Check for Step 2 button or auto-timer
                btn2 = page.query_selector('#BUQeFzS button')
                if btn2:
                    print("[*] Found Step 2 button, clicking...")
                    btn2.click()
                
                # Step 2 countdown is 15 seconds
                for s2 in range(30):
                    time.sleep(1)
                    try:
                        s2_text = page.eval_on_selector('.whatoncode', 'el => el.innerText').strip()
                    except Exception:
                        s2_text = ""
                    if s2 % 3 == 0 or 'Mã' in s2_text or 'Chưa' in s2_text:
                        print(f"  [Step 2 {s2:02d}s] {s2_text.replace(chr(10), ' | ')}")
                    
                    if "Mã KM" in s2_text:
                        for l in s2_text.split('\n'):
                            if "Mã KM" in l:
                                found_code = l.replace("Mã KM:", "").replace("Mã KM", "").strip()
                                break
                        if found_code:
                            print(f"\n🎉 CODE ACQUIRED IN STEP 2: {found_code}")
                            with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_sponsor_code.txt', 'w', encoding='utf-8') as f:
                                f.write(found_code)
                            break
                break
            else:
                print("[!] Could not find internal link!")

        if "Mã KM" in status_text:
            lines = [l.strip() for l in status_text.split('\n') if l.strip()]
            for l in lines:
                if "Mã KM" in l or (len(l) == 6 and l.isalnum()):
                    found_code = l.replace("Mã KM:", "").replace("Mã KM", "").strip()
                    break
            print(f"\n🎉 CODE ACQUIRED: {found_code}")
            with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_sponsor_code.txt', 'w', encoding='utf-8') as f:
                f.write(found_code)
            break

    time.sleep(3)
    browser.close()

    if found_code:
        print("\nSUCCESS! Code saved to fresh_sponsor_code.txt")
    else:
        print("\nCountdown completed without code.")
