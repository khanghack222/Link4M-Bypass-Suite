import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    context = browser.new_context()
    page = context.new_page()

    final_url = None

    def on_resp(resp):
        global final_url
        if 'get-link-info' in resp.url or 'check-captcha' in resp.url:
            try:
                data = resp.json()
                print('\n[LINK4M RESPONSE]:', data)
                if data.get('success') and data.get('url'):
                    final_url = data.get('url')
                    print(f'\n🎉🎉 DESTINATION LINK EXTRACTED: {final_url} 🎉🎉')
            except Exception:
                pass

    page.on('response', on_resp)

    print("[1] Opening Link4M: https://link4m.net/AVsQ2rd3 ...")
    page.goto('https://link4m.net/AVsQ2rd3')

    # Wait for the password input to appear and fill it
    print("[2] Waiting for password input...")
    page.wait_for_selector('input[name="password"]', timeout=15000)
    page.fill('input[name="password"]', 'JVxusD')
    print("[*] Successfully filled sponsor code: JVxusD")

    # Scroll down so captcha is clearly visible
    page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')

    print("\n>>> Please tick the reCAPTCHA box in the opened browser window! <<<")

    for sec in range(90):
        time.sleep(1)
        if final_url:
            break
        # Also check if get-link button is ready
        get_link_btn = page.query_selector('a.get-link:not(.disabled)')
        if get_link_btn:
            href = get_link_btn.get_attribute('href')
            if href and href.startswith('http') and 'link4m' not in href:
                final_url = href
                print(f'\n🎉🎉 DESTINATION LINK EXTRACTED FROM BUTTON: {final_url} 🎉🎉')
                break
            else:
                get_link_btn.click()

    if final_url:
        print("\nSUCCESS! FINAL DESTINATION URL:", final_url)
        with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination_url.txt', 'w', encoding='utf-8') as f:
            f.write(final_url)
    else:
        print("\nTimed out or captcha not clicked.")

    time.sleep(3)
    browser.close()
