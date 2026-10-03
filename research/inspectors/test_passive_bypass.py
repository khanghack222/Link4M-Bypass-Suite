import sys, time, re
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    traffic_key = None
    def route_frame_js(route):
        res = route.fetch()
        text = res.text()
        text = text.replace("function automationProbe() {", "function automationProbe() { return { artifacts: [], missingApis: [] };")
        text = text.replace("function webglInfo() {", "function webglInfo() { return { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)' };")
        text = text.replace("webdriver: navigator.webdriver === true,", "webdriver: false,")
        text = text.replace("untrustedEvents: behavior.untrustedEvents,", "untrustedEvents: 0,")
        text = text.replace("mouseEvents: behavior.mouseEvents,", "mouseEvents: Math.floor(Math.random() * 50) + 80,")
        text = text.replace("timeToClickMs: behavior.timeToClickMs,", "timeToClickMs: Math.floor(Math.random() * 1000) + 2500,")
        text = text.replace("pauseBeforeClickMs: behavior.pauseBeforeClickMs,", "pauseBeforeClickMs: Math.floor(Math.random() * 400) + 600,")
        text = text.replace("clickOffsetPx: behavior.clickOffsetPx,", "clickOffsetPx: { x: 12, y: 14 },")
        route.fulfill(response=res, body=text)
        
    def route_traffic_js(route):
        global traffic_key
        res = route.fetch()
        text = res.text()
        m = re.search(r"var\s+traffic_key\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m: traffic_key = m.group(1)
        text = text.replace('var detectIncognito = function () {', 'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {')
        text = text.replace('document.getElementById("xacthucButton").style.display = "block";', 'if (!document.getElementById("xacthucButton")) { showTrackingMessage(""); } document.getElementById("xacthucButton").style.display = "block";')
        text = text.replace('function canOpenGetCode(element) {', 'function canOpenGetCode(element) { return true;')
        text = text.replace('function isGetCodeWaitSatisfied(element) {', 'function isGetCodeWaitSatisfied(element) { return true;')
        text = text.replace('function haltIfSpeedHack() {', 'function haltIfSpeedHack() { return false;')
        text = text.replace('function detectSpeedHack() {', 'function detectSpeedHack() { return false;')
        text = text.replace('function checkButtonClick(step = 4){', 'window.__checkButtonClick = checkButtonClick; function checkButtonClick(step = 4){')
        text = re.sub(r"checkScrollUpDown\w*\([^)]*\);\s*return true;", "return false;", text)
        text = re.sub(r"checkClickManHinh\w*\([^)]*\);\s*return true;", "return false;", text)
        route.fulfill(response=res, body=text)
    
    page.route('**/frame.js', route_frame_js)
    page.route('**/Traffic/Index/*', route_traffic_js)
    page.route('**/traffic/index/*', route_traffic_js)
    
    def on_res(r):
        if any(k in r.url for k in ['verify_passive', 'solve', 'getcode', 'captcha-nonce']):
            try:
                print(f'[NET API] {r.status} {r.url[:70]} -> {r.text()[:150]}')
            except Exception:
                pass
    page.on('response', on_res)
    
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    time.sleep(2)
    
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    btn_span.click(force=True)
    time.sleep(2)
    
    page.evaluate('() => window.__checkButtonClick(4)')
    frame_el = page.wait_for_selector('iframe[src*="sslip.io"], iframe[src*="frame.html"]', timeout=30000)
    cf = frame_el.content_frame()
    time.sleep(1)
    cf.click('#box', force=True)
    
    for w in range(15):
        time.sleep(1)
        token = page.evaluate('''() => {
            const api = window.hcaptcha || window.qcaptcha;
            return api && typeof api.getResponse === 'function' ? api.getResponse() : null;
        }''')
        if token:
            print(f'[🎉] PASSIVE TOKEN SUCCESS: {token[:40]}...')
            # Click verify button
            page.evaluate('''() => {
                for (const b of document.querySelectorAll('button')) {
                    if (b.innerText.includes('Xác thực và lấy mã')) {
                        b.click();
                        break;
                    }
                }
            }''')
            time.sleep(3)
            break
            
    browser.close()
