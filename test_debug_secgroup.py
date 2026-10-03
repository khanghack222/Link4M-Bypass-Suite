import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def on_page_created(pg):
        pg.on("request", lambda r: print(f"REQ: {r.method} {r.url[:120]}"))
        pg.on("response", lambda r: print(f"RESP ({r.status}): {r.url[:120]}"))
        pg.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    context.on("page", on_page_created)

    from sponsor import _solve_single_sponsor
    res = _solve_single_sponsor(context, "https://secgroup.vn")
    print("\nFINAL RESULT:", res)
    browser.close()
