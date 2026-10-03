from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://theater-teig.at/', timeout=25000, wait_until='commit')
    page.wait_for_selector('#trade-d-btn', timeout=15000)
    
    with open('src/core/andanh.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
    page.evaluate("window.detectIncognito = async () => ({ isPrivate: false, browserName: 'Chrome' });")
    with open('src/core/btd.js', 'r', encoding='utf-8') as f:
        page.evaluate(f"(() => {{ {f.read()} }})()")
        
    print("Testing verifyNexusEnv directly...")
    res = page.evaluate("""async () => {
        try {
            // Test verifyNexusEnv
            const gate = "https://dr-client.gtraffic.io/api/code/";
            const rid = "test-rid-12345";
            const ok = await verifyNexusEnv(gate, rid);
            return {
                ok: ok,
                challengeVal: window.__browser_challenge_ok
            };
        } catch(e) {
            return { error: e.toString() };
        }
    }""")
    print('res:', res)
    b.close()
