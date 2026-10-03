from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://hitclub.cards', timeout=20000, wait_until='domcontentloaded')
    links = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(h => h.includes('hitclub.cards') && h.length > 25);
    }""")
    print('Links on hitclub.cards:', links[:10])
    scripts = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
    }""")
    print('Scripts on hitclub.cards:', scripts)
    b.close()
