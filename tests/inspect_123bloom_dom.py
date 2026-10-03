import time
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "https://123bloom.com"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720}
    )
    page = context.new_page()
    page.goto(URL, wait_until="domcontentloaded", referer="https://www.google.com/")
    time.sleep(3)

    # Scroll to bottom
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    btn = page.locator("#traffic-button, .traffic-button, [class*='traffic-button']")
    print("Found traffic button:", btn.count())
    if btn.count() > 0:
        btn.first.click()
        print("Clicked button! Waiting 3s...")
        time.sleep(3)

        # Check what elements appeared
        html = page.content()
        with open("data/temp/123bloom_after_click.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Saved HTML to data/temp/123bloom_after_click.html")
        page.screenshot(path="data/temp/123bloom_after_click.png")
        print("Screenshot saved to data/temp/123bloom_after_click.png")
    browser.close()
