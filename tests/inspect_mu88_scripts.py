from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://mu88.fund', timeout=25000, wait_until='domcontentloaded')
    time.sleep(2)
    scripts = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('script')).map(s => s.src || s.innerHTML.substring(0, 150));
    }""")
    print("Scripts on mu88.fund:")
    for s in scripts:
        print("  -", s[:120])
    b.close()
