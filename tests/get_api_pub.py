from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    api_pub = page.evaluate("""() => {
        try {
            return window.useNuxtApp ? window.useNuxtApp().$config.public.api_public : null;
        } catch(e) {
            return e.toString();
        }
    }""")
    print('api_pub:', api_pub)
    
    # Also inspect document cookies / localStorage / sessionStorage for rid
    storage = page.evaluate("""() => {
        return {
            cookies: document.cookie,
            session: { ...sessionStorage },
            local: { ...localStorage }
        };
    }""")
    print('storage:', storage)
    b.close()
