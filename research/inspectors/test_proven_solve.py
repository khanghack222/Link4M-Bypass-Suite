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

def find_odd_tile(urls):
    args_list = [(i, u) for i, u in enumerate(urls)]
    feats = list(executor.map(lambda x: analyze_tile(x[0], x[1]), args_list))
    feats.sort(key=lambda x: x[0])
    print('[+] Tile features:', feats)
    
    # 1. By vertices
    v_counts = [f[1] for f in feats]
    for i, v in enumerate(v_counts):
        if v_counts.count(v) == 1 and v > 0:
            return i
            
    # 2. By circularity
    c_counts = [round(f[2], 1) for f in feats]
    for i, c in enumerate(c_counts):
        if c_counts.count(c) == 1 and c > 0:
            return i
            
    # 3. By area
    areas = [f[3] for f in feats]
    median_a = np.median(areas) if areas else 0
    diffs = [abs(a - median_a) for a in areas]
    return int(np.argmax(diffs))

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
        elif 'solve' in r.url:
            try:
                print('[NET API] /v1/solve:', r.status, r.text()[:120])
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
    
    frame_el = page.wait_for_selector('iframe[src*="sslip.io"], iframe[src*="frame.html"]', timeout=30000)
    print('[🎉] Iframe attached!')
    time.sleep(2)
    
    cf = frame_el.content_frame()
    if cf:
        print('[+] Clicking #box in QCaptcha frame...')
        cf.click('#box', force=True)
        print('[+] Clicked #box!')
        
    # Monitor challenge & solve
    solved = False
    for tick in range(35):
        time.sleep(1)
        
        # 1. Check if token already granted
        token = page.evaluate('''() => {
            const api = window.hcaptcha || window.qcaptcha;
            return api && typeof api.getResponse === 'function' ? api.getResponse() : null;
        }''')
        if token:
            print(f'[🎉] Token Ready on tick {tick+1}: {token[:40]}...')
            # Click verify button on sponsor page
            page.evaluate('''() => {
                for (const b of document.querySelectorAll('button')) {
                    if (b.innerText.includes('Xác thực và lấy mã')) {
                        b.click();
                        break;
                    }
                }
            }''')
            time.sleep(2)
            break
            
        # 2. Check challenge type
        info = cf.evaluate('''() => {
            const prompt = document.querySelector('.qc-prompt')?.innerText || '';
            const imgs = document.querySelectorAll('.qc-tile img');
            const skip = document.querySelector('#qc-skip');
            const submit = document.querySelector('#qc-submit');
            return {
                prompt: prompt,
                num_imgs: imgs.length,
                img_urls: Array.from(imgs).map(i => i.src),
                has_skip: !!skip,
                has_submit: !!submit
            };
        }''')
        
        prompt = (info.get('prompt') or '').lower()
        num_imgs = info.get('num_imgs', 0)
        
        if any(k in prompt for k in ['khối', 'trên xuống', 'bên trên', 'chữ thập', 'bao nhiêu']):
            print(f'  [Tick {tick+1}] Skipping non-grid prompt: {prompt}...')
            try:
                cf.click('#qc-skip', force=True)
            except Exception:
                pass
            time.sleep(1.5)
            continue
            
        if num_imgs == 9 and not solved:
            print(f'[+] Detected 9-grid challenge on tick {tick+1}! Prompt: {prompt}')
            odd_i = find_odd_tile(info['img_urls'])
            print(f'[🎯] Selecting odd tile: {odd_i}')
            try:
                cf.click(f".qc-tile[data-i='{odd_i}']", force=True)
            except Exception:
                cf.evaluate(f'(i) => document.querySelector(`.qc-tile[data-i="${{i}}"]`)?.click()', odd_i)
            time.sleep(0.4)
            print('[*] Submitting answer via #qc-submit...')
            try:
                cf.click('#qc-submit', force=True)
            except Exception:
                cf.evaluate('() => document.querySelector("#qc-submit")?.click()')
            solved = True
            time.sleep(1.5)
            
    # Wait for getcode
    for _ in range(15):
        if extracted_layma_code:
            break
        time.sleep(1)
        
    print('\n' + '='*50)
    print(f'🎉 FINAL EXTRACTED LAYMA CODE: {extracted_layma_code}')
    print('='*50 + '\n')
    browser.close()
