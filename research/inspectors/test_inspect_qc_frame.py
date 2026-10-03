import sys, time, re
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    page.on('dialog', lambda d: (print(f'[DIALOG] {d.type}: {d.message}'), d.dismiss()))
    page.on('console', lambda m: print(f'[CONSOLE] {m.type}: {m.text}'))
    
    traffic_key = None
    def route_traffic_js(route):
        global traffic_key
        res = route.fetch()
        text = res.text()
        m = re.search(r"var\s+traffic_key\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            traffic_key = m.group(1)
        
        # 1. Bypass incognito
        text = text.replace(
            'var detectIncognito = function () {',
            'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {'
        )
        # 2. Fix null xacthucButton crash
        text = text.replace(
            'document.getElementById("xacthucButton").style.display = "block";',
            'if (!document.getElementById("xacthucButton")) { showTrackingMessage(""); } document.getElementById("xacthucButton").style.display = "block";'
        )
        # 3. Bypass wait checks
        text = text.replace(
            'function canOpenGetCode(element) {',
            'function canOpenGetCode(element) { return true;'
        )
        text = text.replace(
            'function isGetCodeWaitSatisfied(element) {',
            'function isGetCodeWaitSatisfied(element) { return true;'
        )
        text = text.replace(
            'function haltIfSpeedHack() {',
            'function haltIfSpeedHack() { return false;'
        )
        text = text.replace(
            'function detectSpeedHack() {',
            'function detectSpeedHack() { return false;'
        )
        
        # 4. Expose functions
        text = text.replace(
            'function checkButtonClick(step = 4){',
            'window.__checkButtonClick = checkButtonClick; function checkButtonClick(step = 4){'
        )
        
        # 5. Bypass scroll & click screen blockers
        text = re.sub(r"checkScrollUpDown\w*\([^)]*\);\s*return true;", "return false;", text)
        text = re.sub(r"checkClickManHinh\w*\([^)]*\);\s*return true;", "return false;", text)
        
        route.fulfill(response=res, body=text)
    
    page.route('**/Traffic/Index/*', route_traffic_js)
    page.route('**/traffic/index/*', route_traffic_js)
    
    def on_res(r):
        if any(k in r.url for k in ['layma.net', 'sslip.io', 'getcode']):
            try:
                print(f'[NET] {r.status} {r.url[:90]} -> {r.text()[:120]}')
            except Exception:
                pass
    page.on('response', on_res)
    
    print('[*] Navigating to onlinejob.com.co...')
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    time.sleep(2)
    
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    if btn_span.count() > 0:
        btn_span.click(force=True)
        print('[+] Button clicked!')
        
    time.sleep(2)
    
    print('[*] Triggering checkButtonClick(4)...')
    page.evaluate('''() => {
        if (typeof window.__checkButtonClick === 'function') {
            window.__checkButtonClick(4);
        }
    }''')
    
    # Wait for frame
    qc_frame = None
    for _ in range(15):
        time.sleep(1)
        for fr in page.frames:
            if '103-141-140-153' in fr.url or 'frame.html' in fr.url:
                qc_frame = fr
                break
        if qc_frame:
            break
            
    if qc_frame:
        print('[+] Found QC Frame:', qc_frame.url)
        time.sleep(2)
        # Inspect frame content
        body_html = qc_frame.evaluate('() => document.body.innerHTML')
        print(f'[+] Frame body HTML ({len(body_html)} chars):', body_html[:400])
        
        # Look for buttons or tiles inside frame
        info = qc_frame.evaluate('''() => {
            return {
                buttons: Array.from(document.querySelectorAll('button, input, [role="button"]')).map(b => ({
                    id: b.id,
                    text: b.innerText,
                    tag: b.tagName,
                    cls: b.className
                })),
                tiles: document.querySelectorAll('.qc-tile').length,
                checkbox: !!document.querySelector('#checkbox, input[type="checkbox"], .anchor')
            };
        }''')
        print('[+] Elements inside QCaptcha frame:', info)
    else:
        print('[!] No QC frame found.')
        
    page.screenshot(path='qc_frame_inspect.png')
    browser.close()
