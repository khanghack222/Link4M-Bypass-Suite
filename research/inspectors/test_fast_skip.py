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
    time.sleep(1)
    
    page.locator(f"[id='{traffic_key}'] span").first.click(force=True)
    time.sleep(1)
    
    page.evaluate('() => window.__checkButtonClick(4)')
    frame_el = page.wait_for_selector('iframe[src*="sslip.io"], iframe[src*="frame.html"]', timeout=30000)
    time.sleep(2)
    cf = frame_el.content_frame()
    cf.click('#box', force=True)
    
    for tick in range(15):
        time.sleep(1)
        st = cf.evaluate('''() => {
            const prompt = document.querySelector('.qc-prompt')?.innerText || '';
            const skip = document.getElementById('qc-skip');
            const submit = document.getElementById('qc-submit');
            const tiles = document.querySelectorAll('.qc-tile');
            return { prompt, has_skip: !!skip, num_tiles: tiles.length };
        }''')
        print(f'  Tick {tick+1}:', st)
        if st.get('has_skip') and 'khối' in st.get('prompt', ''):
            print('[*] Clicking skip via evaluate...')
            cf.evaluate("() => document.getElementById('qc-skip')?.click()")
            
    browser.close()
