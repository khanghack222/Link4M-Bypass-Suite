import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    )
    page = browser.new_page(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        extra_http_headers={'referer': 'https://www.google.com/'}
    )
    print("Navigating to https://tylenhacai100.io ...")
    page.goto('https://tylenhacai100.io', wait_until='networkidle')
    time.sleep(2)

    # Scroll to bottom
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)

    # Check for what-on widget or button
    content = page.content()
    with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/sponsor_page.html', 'w', encoding='utf-8') as f:
        f.write(content)

    print("HTML saved, length:", len(content))

    # Look for button
    buttons = page.query_selector_all('button, a, div[onclick], span[onclick]')
    for b in buttons:
        text = b.inner_text().strip()
        if any(w in text.lower() for w in ['lấy mã', 'lay ma', 'mã', 'code']):
            print("Found button candidate:", text, b.evaluate('el => el.outerHTML[:200]'))

    browser.close()
