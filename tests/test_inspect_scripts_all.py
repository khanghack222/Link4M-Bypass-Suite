from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    res = page.evaluate("""async () => {
        try {
            window.__NUXT__ = window.__NUXT__ || {};
            window.__NUXT__.config = window.__NUXT__.config || {
                public: {
                    baseUrl: "https://direct.gtraffic.io",
                    api_public: "https://dr-client.gtraffic.io/",
                    api_private: "https://dr-manager.gtraffic.io/",
                    api_login: "https://drsso.gtraffic.io/"
                },
                app: { baseURL: "/", buildAssetsDir: "/_nuxt/", cdnURL: "" }
            };
            const mod = await import('https://direct.gtraffic.io/_nuxt/CevgXdIP.js');
            return { success: true, keys: Object.keys(mod).slice(0, 10) };
        } catch(e) {
            return { error: e.toString() };
        }
    }""")
    print('import result with config:', res)
    b.close()
