import sys, time, re, io, requests, json
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
import cv2
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

executor = ThreadPoolExecutor(max_workers=9)
s_http = requests.Session()

def analyze_tile(idx, url):
    try:
        r = s_http.get(url, timeout=5)
        im = Image.open(io.BytesIO(r.content)).convert('RGB')
        arr = np.array(im)
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        mask = (hsv[:, :, 1] > 30) | (hsv[:, :, 2] < 150)
        mask_u8 = mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return (idx, 0, 0, 0)
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.035 * peri, True)
        num_v = len(approx)
        circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
        return (idx, num_v, round(circ, 2), round(area, 1))
    except Exception as e:
        return (idx, 0, 0, 0)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
        ]
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 720}
    )
    page = context.new_page()
    
    traffic_key = None
    def route_frame_js(route):
        res = route.fetch()
        text = res.text()
        text = text.replace('function renderChallenge(ch) {', 'window.__qc_ch = ch; function renderChallenge(ch) {')
        text = text.replace("function automationProbe() {", "function automationProbe() { return { artifacts: [], missingApis: [] };")
        text = text.replace("function webglInfo() {", "function webglInfo() { return { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)' };")
        text = text.replace("webdriver: navigator.webdriver === true,", "webdriver: false,")
        text = text.replace("untrustedEvents: behavior.untrustedEvents,", "untrustedEvents: 0,")
        text = text.replace("mouseEvents: behavior.mouseEvents,", "mouseEvents: Math.floor(Math.random() * 50) + 80,")
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
    
    extracted_layma_code = None
    def on_res(r):
        global extracted_layma_code
        if 'getcode' in r.url:
            try:
                data = r.json()
                print('[🎉 NET API] /api/traffic/getcode response:', data)
                c = data.get('html')
                if c and 'không hợp lệ' not in str(c):
                    extracted_layma_code = str(c).strip()
            except Exception:
                pass
    page.on('response', on_res)
    
    print('[*] Navigating to onlinejob.com.co...')
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    time.sleep(2)
    
    btn_span = page.locator(f"[id='{traffic_key}'] span").first
    btn_span.click(force=True)
    time.sleep(2)
    
    print('[*] Triggering checkButtonClick(4)...')
    page.evaluate('() => window.__checkButtonClick(4)')
    
    print('[*] Waiting for iframe[src*="sslip.io"]...')
    frame_el = page.wait_for_selector('iframe[src*="sslip.io"], iframe[src*="frame.html"]', timeout=30000)
    cf = frame_el.content_frame()
    print('[+] Frame attached, waiting for #box...')
    
    # Wait for #box to appear inside frame
    cf.wait_for_selector('#box', timeout=30000)
    print('[*] Clicking checkbox #box...')
    time.sleep(1)
    cf.click('#box', force=True)
    
    # Wait for challenge or passive pass
    ch_data = None
    for tick in range(25):
        time.sleep(1)
        token = page.evaluate('''() => {
            const api = window.hcaptcha || window.qcaptcha;
            return api && typeof api.getResponse === 'function' ? api.getResponse() : null;
        }''')
        if token:
            print(f'[🎉] Token obtained directly: {token[:40]}...')
            break
            
        ch_info = cf.evaluate('''() => {
            if (window.__qc_ch) {
                return {
                    type: window.__qc_ch.type,
                    spec: window.__qc_ch.spec,
                    assets: (window.__qc_ch.assets || []).map(a => a.url)
                };
            }
            return null;
        }''')
        if ch_info and ch_info.get('assets'):
            ch_data = ch_info
            print(f'[+] Detected Challenge on tick {tick+1}: type={ch_info["type"]}, key={ch_info["spec"].get("questionKey")}')
            break
            
    if ch_data and ch_data['type'] in ['grid3x3', 'relational', 'oddoneout']:
        q_key = ch_data['spec'].get('questionKey', '').lower()
        assets = ch_data['assets']
        print(f'[*] Analyzing {len(assets)} assets for questionKey: {q_key}...')
        features = list(executor.map(lambda x: analyze_tile(x[0], x[1]), enumerate(assets)))
        features.sort(key=lambda x: x[0])
        print('[+] Features:', features)
        
        ans = []
        if 'hexagon' in q_key:
            ans = [f[0] for f in features if f[1] == 6]
        elif 'pentagon' in q_key:
            ans = [f[0] for f in features if f[1] == 5]
        elif 'square' in q_key or 'rectangle' in q_key:
            ans = [f[0] for f in features if f[1] == 4]
        elif 'triangle' in q_key:
            ans = [f[0] for f in features if f[1] == 3]
        elif 'circle' in q_key:
            ans = [f[0] for f in features if f[2] > 0.75]
        else:
            counts = [f[1] for f in features]
            for i, c in enumerate(counts):
                if counts.count(c) == 1:
                    ans = [i]
                    break
                    
        if not ans:
            ans = [0]
            
        print(f'[+] Target tiles to select: {ans}')
        for idx in ans:
            tile_sel = f".qc-tile[data-i='{idx}']"
            try:
                cf.click(tile_sel, timeout=3000)
            except Exception:
                cf.evaluate(f'(sel) => document.querySelector(sel)?.click()', tile_sel)
            time.sleep(0.3)
            
        print('[*] Submitting answers via #qc-submit...')
        try:
            cf.click('#qc-submit', timeout=3000)
        except Exception:
            cf.evaluate('() => document.querySelector("#qc-submit")?.click()')
            
    elif ch_data and ch_data['type'] == 'countshapes':
        print('[*] Countshapes challenge detected, handling click stage or skip...')
        cf.click('#qc-skip', force=True)
        
    # Wait for token
    for _ in range(20):
        time.sleep(1)
        token = page.evaluate('''() => {
            const api = window.hcaptcha || window.qcaptcha;
            return api && typeof api.getResponse === 'function' ? api.getResponse() : null;
        }''')
        if token:
            print(f'[🎉] QCaptcha Token is Verified: {token[:40]}... Triggering getcode!')
            page.evaluate('''() => {
                for (const b of document.querySelectorAll('button')) {
                    if (b.innerText.includes('Xác thực và lấy mã')) {
                        b.click();
                        break;
                    }
                }
            }''')
            break
            
    # Wait for getcode
    for _ in range(15):
        if extracted_layma_code:
            break
        time.sleep(1)
        
    print('\n' + '='*50)
    print(f'🎉 FINAL EXTRACTED LAYMA CODE: {extracted_layma_code}')
    print('='*50 + '\n')
    browser.close()
