from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://mu88.fund', timeout=25000, wait_until='domcontentloaded')
    time.sleep(2)
    # Scroll down to bottom
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    
    btn = page.locator('#trade-d-btn, .trade-d-btn-container').first
    print("Clicking trade-d-btn...")
    btn.click(force=True)
    
    for i in range(1, 10):
        time.sleep(1)
        res = page.evaluate("""() => {
            const el = document.querySelector('#trade-d-btn, .trade-d-btn-container, #trade-d-btn__content');
            return {
                text: el ? el.innerText : null,
                dataset: el ? el.dataset : null,
                html: el ? el.innerHTML.substring(0, 150) : null
            };
        }""")
        print(f"Sec {i}: {res}")
    b.close()
