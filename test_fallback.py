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

    # Block get-advertise to force fallback to pure reCAPTCHA!
    page.route('**/api/campaign/get-advertise', lambda route: route.abort())

    print("Navigating to https://link4m.org/go/F2EnICG with get-advertise BLOCKED...")
    page.goto('https://link4m.org/go/F2EnICG', wait_until='networkidle')
    time.sleep(3)

    pw = page.query_selector('input.password')
    print("Password input exists:", bool(pw))

    main_form = page.query_selector('#main-form')
    print("Main form exists:", bool(main_form))
    if main_form:
        print("Main form HTML:", main_form.evaluate('el => el.outerHTML'))

    recaptcha_div = page.query_selector('#recaptcha')
    print("Recaptcha div exists:", bool(recaptcha_div))

    browser.close()
