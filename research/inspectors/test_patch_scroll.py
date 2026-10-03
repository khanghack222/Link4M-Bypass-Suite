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
        
        # 1. Extract traffic key
        m = re.search(r"var\s+traffic_key\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m: traffic_key = m.group(1)
        
        # 2. Neutralize incognito detection
        text = text.replace(
            "var detectIncognito = function () {",
            'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {'
        )
        
        # 3. Neutralize scroll pauses & click screen pauses
        text = re.sub(r"checkScrollUpDown\w*\([^)]*\);\s*return true;", "return false;", text)
        text = re.sub(r"checkClickManHinh\w*\([^)]*\);\s*return true;", "return false;", text)
        
        route.fulfill(response=res, body=text)
    
    page.route("**/Traffic/Index/*", route_traffic_js)
    
    print("[*] Navigating to https://onlinejob.com.co...")
    page.goto("https://onlinejob.com.co", wait_until="domcontentloaded")
    time.sleep(2)
    
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    print("[+] Clicking LẤY MÃ button...")
    btn_span.click(force=True)
    
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
        if sec % 5 == 0 or (rem is not None and rem <= 5):
            print(f"  [T+{sec}s] Remaining: {rem}")
        if rem is not None and rem <= 0:
            print("🎉 COUNTDOWN REACHED ZERO!")
            break
            
    browser.close()