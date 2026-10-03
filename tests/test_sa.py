from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://mu88.fund', timeout=25000, wait_until='networkidle')
    res = page.evaluate("""() => {
        return {
            hasSa: typeof sa !== 'undefined',
            hasDetectIncognito: typeof detectIncognito !== 'undefined',
            hasAndanh: !!document.querySelector('script[src*="andanh"]')
        };
    }""")
    print('res:', res)
    b.close()
