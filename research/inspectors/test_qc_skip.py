import sys, time, re
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
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
    
    page.route('**/Traffic/Index/*', route_traffic_js)
    page.route('**/traffic/index/*', route_traffic_js)
    
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    time.sleep(2)
    
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    btn_span.click(force=True)
    time.sleep(2)
    
    page.evaluate('() => window.__checkButtonClick(4)')
    frame_el = page.wait_for_selector('iframe[src*="sslip.io"], iframe[src*="frame.html"]', timeout=30000)
    cf = frame_el.content_frame()
    cf.click('#box', force=True)
    
    print('[*] Waiting for challenge dialog or token...')
    for w in range(25):
        time.sleep(1)
        token = page.evaluate('''() => {
            const api = window.hcaptcha || window.qcaptcha;
            return api && typeof api.getResponse === 'function' ? api.getResponse() : null;
        }''')
        if token:
            print(f'[🎉] Token found: {token[:40]}...')
            break
            
        has_skip = cf.evaluate('''() => {
            const sk = document.querySelector('#qc-skip');
            const sub = document.querySelector('#qc-submit');
            const prompt = document.querySelector('.qc-prompt, [class*="prompt"], [class*="header"]')?.innerText;
            return {
                skip: !!sk,
                submit: !!sub,
                prompt: prompt,
                tiles: document.querySelectorAll('.qc-tile').length,
                text: document.body.innerText.slice(0, 100)
            };
        }''')
        print(f'  [Tick {w+1}] Frame status:', has_skip)
        
        if has_skip.get('skip'):
            print('[*] Clicking #qc-skip...')
            cf.click('#qc-skip', force=True)
            time.sleep(2)
            
    browser.close()
