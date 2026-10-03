from patchright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    
    # In page1 context, we have full cookies, origin, referer, session state
    # Let's inspect what happens if we execute fetch('api/url/tracking-url') from within page1!
    res = page.evaluate("""async () => {
        try {
            // Find inputs and values
            const inp = document.querySelector('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])');
            if (inp) {
                inp.value = 'DW54qX6C';
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
            
            // Try fetching tracking-url directly from page1 context
            const baseApi = "https://dr-client.gtraffic.io/";
            // Let's get rid from NUXT state or cookies
            let rid = null;
            if (window.__NUXT_DATA__) {
                for (const item of window.__NUXT_DATA__) {
                    if (typeof item === 'string' && item.length === 36 && item.includes('-')) {
                        rid = item;
                        break;
                    }
                }
            }
            
            return {
                rid: rid,
                hasFetch: typeof fetch !== 'undefined',
                href: window.location.href
            };
        } catch(e) {
            return { error: e.toString() };
        }
    }""")
    print('res:', res)
    b.close()
