from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.add_init_script("""
        window.__NUXT__ = window.__NUXT__ || {};
        window.__NUXT__.config = {
            public: {
                baseUrl: "https://direct.gtraffic.io",
                api_public: "https://dr-client.gtraffic.io/",
                api_private: "https://dr-manager.gtraffic.io/",
                api_login: "https://drsso.gtraffic.io/",
                webName: "Gtraffic",
                webDescription: ""
            },
            app: { baseURL: "/", buildAssetsDir: "/_nuxt/", cdnURL: "" }
        };
    """)
    page.on('console', lambda m: print(f'[CONSOLE] {m.text}'))
    page.on('request', lambda r: print(f'[REQ {r.method}] {r.url}') if 'api' in r.url else None)
    page.on('response', lambda r: print(f'[RESP {r.status}] {r.url}') if 'api' in r.url and 'recaptcha' not in r.url else None)
    
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    
    inp = page.locator('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])').first
    inp.fill('TESTCODE')
    
    btn = page.locator('button:has-text("NHẬP MÃ XÁC NHẬN")').first
    print("Clicking submit button...")
    btn.click()
    
    for s in range(1, 15):
        time.sleep(1)
        if s % 3 == 0:
            print(f"Sec {s} after click, URL: {page.url}")
    b.close()
