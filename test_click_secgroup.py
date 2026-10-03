import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    def on_req(r):
        if "what-on" in r.url or "get_quest" in r.url:
            print(f"[REQ] {r.method} {r.url}")
            if r.post_data:
                print(f"      POST_DATA: {r.post_data}")

    def on_resp(r):
        if "what-on" in r.url or "get_quest" in r.url:
            print(f"[RESP {r.status}] {r.url}")

    page.on("request", on_req)
    page.on("response", on_resp)
    page.on("console", lambda m: print(f"[CONSOLE] {m.text}"))

    page.goto("https://secgroup.vn", referer="https://www.google.com/")
    page.wait_for_timeout(3000)

    print("\n--- CLICKING BUTTON ---")
    btn = page.locator("#fC6by7 button")
    if btn.count() > 0:
        print("Found button! Clicking...")
        btn.click()
    else:
        print("Button not found via locator!")

    # Wait 8s to see what requests happen
    page.wait_for_timeout(8000)

    # Check status of widget
    status = page.evaluate('''() => {
        const el = document.getElementById('fC6by7');
        const whaton = document.querySelector('.whatoncode');
        return {
            el_dataset: el ? {...el.dataset} : null,
            whaton_text: whaton ? whaton.innerText : null
        };
    }''')
    print("STATUS AFTER CLICK:", status)

    browser.close()
