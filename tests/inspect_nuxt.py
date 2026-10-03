import sys
import json
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://gtraffic.io/e_2Qu3i', timeout=30000, wait_until='domcontentloaded')
    nuxt_data = page.evaluate("""() => {
        const nuxtScript = document.getElementById('__NUXT_DATA__');
        if (nuxtScript) {
            try { return JSON.parse(nuxtScript.innerText); } catch(e) { return nuxtScript.innerText; }
        }
        return window.__NUXT__ || null;
    }""")
    with open('data/nuxt_dump.json', 'w', encoding='utf-8') as f:
        json.dump(nuxt_data, f, indent=2, ensure_ascii=False)
    print('Dumped successfully!')
    b.close()
