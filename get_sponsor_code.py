import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

print("=== STEP 1: RETRIEVING SPONSOR CODE FROM tylenhacai100.io ===")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        extra_http_headers={'referer': 'https://www.google.com/'}
    )
    page = context.new_page()
    page.goto('https://tylenhacai100.io', wait_until='domcontentloaded')
    time.sleep(3)

    # Scroll down to find button
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)

    btn = page.query_selector('div[id="5zqDZ7qw"] button')
    if not btn:
        btn = page.query_selector('button:has-text("LẤY MÃ")')

    if btn:
        print("[✓] Found button 'LẤY MÃ', clicking...")
        btn.click()
        
        # Monitor countdown
        for second in range(75):
            time.sleep(1)
            btn_text = btn.inner_text().strip()
            if second % 5 == 0 or any(c.isdigit() for c in btn_text):
                print(f"[{second}s] Button state: {btn_text}")
            
            # Check if code appeared (often 6 chars, uppercase/numbers or text)
            div_container = page.query_selector('div[id="5zqDZ7qw"]')
            if div_container:
                container_text = div_container.inner_text().strip()
                if "chờ" not in container_text.lower() and "lấy mã" not in container_text.lower() and len(container_text) > 0:
                    print("🎉 SPONSOR CODE REVEALED:", container_text)
                    with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/sponsor_code.txt', 'w', encoding='utf-8') as f:
                        f.write(container_text)
                    break
    else:
        print("[!] Could not locate 'LẤY MÃ' button!")

    browser.close()
