import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    page = context.new_page()

    # Track all requests/responses
    def on_req(req):
        if 'what-on.com' in req.url:
            print(f'[REQ] {req.method} {req.url}')

    def on_resp(resp):
        if 'what-on.com' in resp.url and 'quest' in resp.url:
            try:
                print(f'[RESP] {resp.url} => {resp.text()}')
            except Exception as e:
                print(f'[RESP] Error reading text: {e}')

    page.on('request', on_req)
    page.on('response', on_resp)

    # Disable page visibility/blur checks
    page.add_init_script('''
        Object.defineProperty(document, 'hidden', { get: () => false });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        window.addEventListener('blur', (e) => e.stopImmediatePropagation(), true);
    ''')

    print("[1] Navigating to https://soikeobongda.life ...")
    page.goto('https://soikeobongda.life', wait_until='networkidle')

    # Find the button inside #BUQeFzS
    widget = page.query_selector('#BUQeFzS')
    if not widget:
        print("[!] #BUQeFzS not found!")
        browser.close()
        sys.exit(1)

    btn = widget.query_selector('button')
    if not btn:
        print("[!] Button inside #BUQeFzS not found!")
        browser.close()
        sys.exit(1)

    print("[2] Found button, clicking...")
    btn.click()

    # Loop and monitor the text inside #BUQeFzS for 75 seconds
    for sec in range(75):
        time.sleep(1)
        try:
            current_text = page.eval_on_selector('#BUQeFzS', 'el => el.innerText').strip()
        except Exception:
            current_text = ""
        
        if sec % 10 == 0 or 'Mã' in current_text or 'Chưa' in current_text:
            print(f"  [{sec:02d}s] Widget text: {current_text}")

        # Check if code appears
        lines = [line.strip() for line in current_text.split('\n') if line.strip()]
        for line in lines:
            if len(line) == 6 and line.isalnum():
                print(f"\n🎯 FOUND CODE: {line}")
                with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_sponsor_code.txt', 'w', encoding='utf-8') as f:
                    f.write(line)
                browser.close()
                sys.exit(0)

    print("\nFinal widget innerHTML:")
    print(page.eval_on_selector('#BUQeFzS', 'el => el.innerHTML'))
    browser.close()
