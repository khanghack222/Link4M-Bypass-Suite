from playwright.sync_api import sync_playwright
import sys
sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://layma.net/Kd1onyItr', wait_until='networkidle')
    print('PAGE TITLE:', page.title())
    print('PAGE TEXT SNIPPET:')
    print(page.inner_text('body')[:1500])
    page.screenshot(path='layma_page_screen.png')
    browser.close()
