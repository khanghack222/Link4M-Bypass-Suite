from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://mu88.fund', timeout=25000, wait_until='domcontentloaded')
    time.sleep(2)
    info = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('#trade-btn-clf, #trade-btn, #traffic-button-no, #trade-d-btn, [id*="trade"], [class*="trade"], [id*="traffic"], [class*="traffic"]'));
        return btns.map(b => ({
            id: b.id,
            cls: b.className,
            text: b.innerText,
            box: b.getBoundingClientRect()
        }));
    }""")
    print("Found elements on mu88.fund:")
    for el in info:
        print(" ", el)
    b.close()
