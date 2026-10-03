import sys, time, re
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    traffic_key = None
    def route_traffic_js(route):
        global traffic_key
        res = route.fetch()
        text = res.text()
        m = re.search(r"var\s+traffic_key\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m: traffic_key = m.group(1)
        text = text.replace(
            "var detectIncognito = function () {",
            'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {'
        )
        text = re.sub(r"checkScrollUpDown\w*\([^)]*\);\s*return true;", "return false;", text)
        text = re.sub(r"checkClickManHinh\w*\([^)]*\);\s*return true;", "return false;", text)
        route.fulfill(response=res, body=text)
    
    page.route("**/Traffic/Index/*", route_traffic_js)
    
    # Intercept API calls
    def on_response(res):
        if any(k in res.url for k in ["getcode", "qcaptcha", "visit", "captcha"]):
            try:
                print(f"[NET API] {res.status} {res.url}: {res.text()[:200]}")
            except:
                pass
    page.on("response", on_response)
    
    print("[*] Navigating to https://onlinejob.com.co...")
    page.goto("https://onlinejob.com.co", wait_until="domcontentloaded")
    time.sleep(2)
    
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    print("[+] Clicking LẤY MÃ button...")
    btn_span.click(force=True)
    
    # Wait for countdown
    for sec in range(70):
        time.sleep(1)
        rem = page.evaluate(f"""() => {{
            const el = document.getElementById('{traffic_key}');
            if (el && el.dataset.time) return parseFloat(el.dataset.time);
            for (const s of document.querySelectorAll('span, div, button')) {{
                const m = (s.innerText || '').match(/Lấy mã sau\\s*(\\d+)/i);
                if (m) return parseFloat(m[1]);
            }}
            return null;
        }}""")
        if rem is not None and rem <= 0:
            print("🎉 COUNTDOWN ZERO! Checking DOM for 15s...")
            break
            
    for wait_tick in range(15):
        time.sleep(1)
        info = page.evaluate(f"""() => {{
            const el = document.getElementById('{traffic_key}');
            const tracking = document.getElementById('trackingMessageContainer');
            const xacthuc = document.getElementById('xacthucButton');
            const retry = document.getElementById('getCodeRetryButton');
            return {{
                el_text: el ? el.innerText : null,
                tracking_text: tracking ? tracking.innerText : null,
                xacthuc_visible: xacthuc ? xacthuc.style.display : null,
                retry_visible: retry ? retry.style.display : null,
                modal_present: !!document.querySelector('.modal, [class*="modal"], [id*="qcaptcha"]')
            }};
        }}""")
        print(f"  [After 0s + {wait_tick+1}s] DOM Info:", info)
        
        # Check if xacthucButton or retryButton can be clicked
        page.evaluate("""() => {
            const xb = document.getElementById('xacthucButton');
            if (xb && xb.style.display !== 'none') xb.click();
            const rb = document.getElementById('getCodeRetryButton');
            if (rb && rb.style.display !== 'none') rb.click();
        }""")
        
        # Check frames for qcaptcha
        for fr in page.frames:
            if "qcaptcha" in fr.url.lower() or "frame." in fr.url:
                print(f"  Found QCaptcha frame: {fr.url[:80]}")
                
    page.screenshot(path="after_zero_screen.png")
    browser.close()