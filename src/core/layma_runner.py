import sys, os, time, re, io, json, requests
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
import cv2
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CORE_DIR, "..", ".."))
ROOT_DIR = BASE_DIR
DEST_FILE = os.path.join(BASE_DIR, "destination_url.txt")
FINAL_DEST_FILE = os.path.join(BASE_DIR, "DESTINATION_FINAL_URL.txt")
CODE_FILE = os.path.join(BASE_DIR, "extracted_code.txt")

try:
    from config import get_chrome_path, copy_to_clipboard
except ImportError:
    def get_chrome_path(): return None
    def copy_to_clipboard(t): pass

executor = ThreadPoolExecutor(max_workers=9)
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
})

def analyze_tile_url(args):
    idx, url = args
    if url.startswith('/'):
        url = 'https://frame.103-141-140-153.sslip.io' + url
    try:
        r = http_session.get(url, timeout=5)
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
    except Exception:
        return (idx, 0, 0, 0)

def run(target_url: str = None, headless: bool = None):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "https://layma.net/pohWNZgba"
    if headless is None:
        headless = False if ("--head" in sys.argv or "-w" in sys.argv or "--window" in sys.argv) else True

    print("=" * 60)
    print(f"🚀 LINK4M / LAYMA BYPASS ENGINE - TARGET: {target_url}")
    print("=" * 60)
    print(f"[*] Target LayMa URL: {target_url}")

    with sync_playwright() as p:
        c_path = get_chrome_path()
        browser = p.chromium.launch(
            executable_path=c_path if c_path and os.path.exists(c_path) else None,
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--window-size=1280,720'
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720}
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            try {
                Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
                Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
                window.hasFocus = () => true;
            } catch (e) {}
        """)

        # 1. Open LayMa page
        page_layma = context.new_page()
        final_destination_url = None
        direct_redirect_url = None

        def on_nav(frame):
            nonlocal final_destination_url
            if frame == page_layma.main_frame:
                u = frame.url
                if u and u.startswith("http") and "layma.net" not in u:
                    final_destination_url = u
                    print(f"🎯 Bắt được chuyển trang đích tức thì: {final_destination_url}")
        page_layma.on("framenavigated", on_nav)

        def on_layma_res(res):
            nonlocal final_destination_url, direct_redirect_url
            u_low = res.url.lower()
            if "checkcode" in u_low:
                try:
                    data = res.json()
                    print(f"[+] LayMa checkcode response: {data}")
                    u = data.get("redirectUrl") or data.get("RedirectUrl") or data.get("url")
                    if u and u.startswith("http"):
                        direct_redirect_url = u
                        print(f"🎯 Nhận redirectUrl từ JSON: {direct_redirect_url}")
                except Exception as e:
                    try:
                        raw = res.text()
                        m_go = re.search(r"https?://[^\s\"\'<>]*/api/traffic/go/[A-Za-z0-9_\-]+", raw)
                        if m_go:
                            direct_redirect_url = m_go.group(0)
                            print(f"🎯 Bắt được direct_redirect_url từ text: {direct_redirect_url}")
                    except Exception:
                        pass

            if "api/traffic/go/" in u_low:
                try:
                    loc = res.headers.get("location")
                    if loc and "layma.net" not in loc:
                        final_destination_url = loc
                        print(f"🎯 Bắt được 302 Location từ api/traffic/go/: {final_destination_url}")
                except Exception:
                    pass
        page_layma.on("response", on_layma_res)

        print(f"[*] Step 1: Navigating to LayMa shortlink: {target_url}...")
        page_layma.goto(target_url, wait_until="domcontentloaded")
        time.sleep(2)

        camp_id = page_layma.locator("#campainId").inner_text().strip() if page_layma.locator("#campainId").count() > 0 else ""
        print(f"[+] Campaign ID on LayMa: {camp_id}")
        if not camp_id or camp_id == "00000000-0000-0000-0000-000000000000":
            print(f"⚠ [LayMa] Link này hiện không có chiến dịch hoạt động hoặc đã hết lượt (Campaign ID: {camp_id}).")
            browser.close()
            return None

        SPONSOR_KEYS = {
            "agilafc.com": "4AzF9IZh9",
            "vijaylaxmigranito.in": "JkfFIYs4i",
            "www.vijaylaxmigranito.in": "JkfFIYs4i",
            "dunchurchsportsandfootballclub.co.uk": "4AzF9IZh9",
        }
        DEAD_SPONSORS = ["go88yt", "go88", "sunwin", "qo88", "lo88", "88yt", "smileitsolutions"]

        def detect_layma_sponsor():
            # Check text in #linkWeb or #linkNoidung first!
            for txt_sel in ['#linkWeb', '#linkNoidung', 'a[href*="http"]']:
                loc = page_layma.locator(txt_sel)
                if loc.count() > 0:
                    try:
                        t = loc.first.inner_text().strip()
                        m = re.search(r'([a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', t)
                        if m and not any(k in m.group(1).lower() for k in ['layma', 'google', 'facebook', 'youtube']):
                            return m.group(1)
                    except Exception:
                        pass

            selectors = ['#linkWeb', '#hinh_nv', 'img.url-hint-image', 'img[src*="/posts/"]', '.box-linkFB-wrap img']
            for sel in selectors:
                loc = page_layma.locator(sel)
                if loc.count() > 0:
                    tmp_ocr = os.path.join(ROOT_DIR, "data", "temp", "layma_linkweb.png")
                    os.makedirs(os.path.dirname(tmp_ocr), exist_ok=True)
                    try:
                        loc.first.screenshot(path=tmp_ocr)
                        from rapidocr_onnxruntime import RapidOCR
                        lines, _ = RapidOCR()(tmp_ocr)
                        if lines:
                            all_texts = [l[1].strip().lower() for l in lines]
                            detected = None
                            # Find domain pattern in OCR lines
                            for t in all_texts:
                                m = re.search(r'([a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', t)
                                if m and not any(k in m.group(1) for k in ['layma', 'google', 'facebook', 'youtube']):
                                    detected = m.group(1)
                                    break
                            if not detected:
                                for t in all_texts:
                                    m2 = re.search(r'([a-zA-Z0-9\-]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', t)
                                    if m2 and len(m2.group(1)) > 4 and not any(k in m2.group(1) for k in ['layma', 'google', 'facebook']):
                                        detected = m2.group(1)
                                        break
                            if detected:
                                # Check if detected domain itself is dead
                                if any(d in detected for d in DEAD_SPONSORS):
                                    return f"dead_{detected}"
                                return detected

                            joined = ' '.join(all_texts)
                            if any(k in joined for k in ['go88', 'qo88', 'lo88']):
                                return "go88yt.com"
                            return all_texts[0]
                    except Exception as e:
                        print(f"[!] OCR error on {sel}: {e}")
            return None

        detected_sponsor = detect_layma_sponsor()
        print(f"[*] OCR detected sponsor domain on page: '{detected_sponsor}'")

        for sw_attempt in range(3):
            if detected_sponsor and detected_sponsor.startswith("dead_"):
                print(f"[!] Sponsor '{detected_sponsor}' không khả dụng / Cloudflare (Lần {sw_attempt + 1}). Tự động đổi nhiệm vụ (#btn-baoloi)...")
                btn_baoloi = page_layma.locator("#btn-baoloi")
                if btn_baoloi.count() > 0:
                    btn_baoloi.click()
                    time.sleep(1)
                    btn_confirm = page_layma.locator("#btnXacNhanDoiNhiemVu")
                    if btn_confirm.count() > 0:
                        btn_confirm.click()
                        print("[*] Đã nhấn xác nhận đổi nhiệm vụ, đợi 8s tải lại campaign mới...")
                        time.sleep(8)
                        page_layma.wait_for_load_state("domcontentloaded")
                        camp_id = page_layma.locator("#campainId").inner_text().strip() if page_layma.locator("#campainId").count() > 0 else ""
                        detected_sponsor = detect_layma_sponsor()
                        print(f"[+] Sau khi đổi: Campaign ID: {camp_id}, Sponsor: '{detected_sponsor}'")
            else:
                break

        sponsor_domain = "agilafc.com"
        traffic_key = "4AzF9IZh9"
        if detected_sponsor:
            clean_dom = re.sub(r'^(?:https?://)?(?:www\.)?', '', detected_sponsor).strip('/')
            for k, v in SPONSOR_KEYS.items():
                if k in detected_sponsor or detected_sponsor in k or k in clean_dom:
                    sponsor_domain = k
                    traffic_key = v
                    break
            else:
                sponsor_domain = clean_dom

        # Check mission type on LayMa (Google search vs Direct link)
        layma_body_text = page_layma.inner_text("body").lower()
        is_direct = "gõ trang web" in layma_body_text or "truy cập liên kết" in layma_body_text or ("từ khóa" not in layma_body_text and "google" not in layma_body_text)
        flatform_target = 'tructiep' if is_direct else 'google'
        print(f"[*] Resolved Sponsor Domain: https://{sponsor_domain} (Traffic Key: {traffic_key}, Platform: {flatform_target})")

        # 2. Open Sponsor page
        page_sponsor = context.new_page()
        extracted_layma_code = None

        def route_frame_js(route):
            res = route.fetch()
            text = res.text()
            text = text.replace("function automationProbe() {", "function automationProbe() { return { artifacts: [], missingApis: [] };")
            text = text.replace("function webglInfo() {", "function webglInfo() { return { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)' };")
            text = text.replace("webdriver: navigator.webdriver === true,", "webdriver: false,")
            text = text.replace("untrustedEvents: behavior.untrustedEvents,", "untrustedEvents: 0,")
            text = text.replace("mouseEvents: behavior.mouseEvents,", "mouseEvents: 142,")
            text = text.replace("solveMs: Math.round(performance.now() - state.startedAt),", "solveMs: Math.max(3800, Math.round(performance.now() - state.startedAt)),")
            text = text.replace("const state = {", "window.__qc_state = null; const state = window.__qc_state = {")
            text = text.replace("async function skipType(reason) {", "window.__qc_skip = skipType; async function skipType(reason) {")
            text = text.replace("async function submit(override, extra = {}) {", "window.__qc_submit = submit; async function submit(override, extra = {}) {")
            route.fulfill(response=res, body=text)

        def route_traffic_js(route):
            res = route.fetch()
            text = res.text()

            # Dynamic flatform based on mission
            text = re.sub(r"var\s+flatform\s*=\s*checkReferer\(referrer\);", f"var flatform = '{flatform_target}';", text)
            text = re.sub(r"flatform\s*=\s*checkReferer\(referrer\);", f"flatform = '{flatform_target}';", text)
            text = text.replace("var flatform = 'tructiep';", f"var flatform = '{flatform_target}';")
            text = text.replace("var flatform = 'google';", f"var flatform = '{flatform_target}';")

            # Force Solution 1 (1 single page, 1 step)
            text = text.replace(
                'randomSolution = Math.floor((Math.random() * 2));',
                'randomSolution = 0;'
            )
            # Bypass incognito
            text = text.replace(
                'var detectIncognito = function () {',
                'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {'
            )
            # Fix DOM container null
            text = text.replace(
                'document.getElementById("xacthucButton").style.display = "block";',
                'var _xb = document.getElementById("xacthucButton"); if (_xb) _xb.style.display = "block";'
            )
            # Bypass wait satisfied check
            text = text.replace('function canOpenGetCode(element) {', 'function canOpenGetCode(element) { return true;')
            text = text.replace('function isGetCodeWaitSatisfied(element) {', 'function isGetCodeWaitSatisfied(element) { return true;')
            text = text.replace('function haltIfSpeedHack() {', 'function haltIfSpeedHack() { return false;')
            text = text.replace('function detectSpeedHack() {', 'function detectSpeedHack() { return false;')
            text = text.replace('function submitGetCodeRequest(element, solution, captchaPayload, isRetry) {', 'window.__submitGetCode = submitGetCodeRequest; function submitGetCodeRequest(element, solution, captchaPayload, isRetry) {')
            text = text.replace('function checkButtonClick(step = 4){', 'window.__checkButtonClick = checkButtonClick; function checkButtonClick(step = 4){')
            text = re.sub(r"checkScrollUpDown\w*\([^)]*\);\s*return true;", "return false;", text)
            text = re.sub(r"checkClickManHinh\w*\([^)]*\);\s*return true;", "return false;", text)
            route.fulfill(response=res, body=text)

        page_sponsor.route("**/frame.js", route_frame_js)
        page_sponsor.route("**/Traffic/Index/*", route_traffic_js)
        page_sponsor.route("**/traffic/index/*", route_traffic_js)

        def on_sponsor_res(res):
            nonlocal extracted_layma_code
            if "/api/traffic/getcode" in res.url:
                try:
                    data = res.json()
                    print(f"[+] /api/traffic/getcode response: {data}")
                    c_val = data.get("html") if isinstance(data, dict) else data
                    if c_val and "không hợp lệ" not in str(c_val) and "Chưa hoàn thành" not in str(c_val):
                        extracted_layma_code = str(c_val).strip()
                        print(f"🎉 SUCCESS! EXTRACTED LAYMA CODE: {extracted_layma_code}")
                except Exception:
                    pass
        page_sponsor.on("response", on_sponsor_res)

        print(f"[*] Step 2: Navigating to sponsor: https://{sponsor_domain} with Google Referer...")
        page_sponsor.goto(
            f"https://{sponsor_domain}",
            referer="https://www.google.com/",
            wait_until="domcontentloaded"
        )
        time.sleep(2)

        # Dynamically detect traffic_key from page scripts
        try:
            detected_key = page_sponsor.evaluate("""() => {
                const s = document.querySelector('script[src*="Traffic/Index"], script[src*="traffic/index"]');
                if (s) {
                    const m = s.src.match(/[Tt]raffic\/[Ii]ndex\/([A-Za-z0-9_-]+)/);
                    if (m) return m[1];
                }
                return null;
            }""")
            if detected_key:
                traffic_key = detected_key
                print(f"[+] Tự động phát hiện Traffic Key từ script: {traffic_key}")
        except Exception:
            pass

        # Click the LẤY MÃ button
        time.sleep(1.0)
        clicked_res = page_sponsor.evaluate(f"""() => {{
            let el = document.getElementById('{traffic_key}');
            let foundKey = '{traffic_key}';
            if (!el) {{
                const s = document.querySelector('script[src*="Traffic/Index"], script[src*="traffic/index"]');
                if (s) {{
                    const m = s.src.match(/[Tt]raffic\/[Ii]ndex\/([A-Za-z0-9_-]+)/);
                    if (m) {{
                        foundKey = m[1];
                        el = document.getElementById(m[1]);
                    }}
                }}
            }}
            if (!el) {{
                el = document.querySelector('[class*="Ran"], button[id*="Az"], div[id*="Az"], div[id*="Jkf"], div[id*="DrD"], div[id]');
                if (el && el.id) foundKey = el.id;
            }}
            if (el) {{
                const sp = el.querySelector('span') || el;
                sp.click();
                return {{ success: true, key: foundKey }};
            }}
            return {{ success: false, key: foundKey }};
        }}""")
        if clicked_res and clicked_res.get('success'):
            if clicked_res.get('key'):
                traffic_key = clicked_res['key']
            print(f"⚡ Kích hoạt nút LẤY MÃ thành công (Key: {traffic_key})! Bắt đầu đếm ngược 60s...")
        else:
            print("[!] Thử query selector click nút lấy mã...")
            page_sponsor.evaluate("() => { const b = document.querySelector('[class*=\"Ran\"], button[id], div[id*=\"Az\"], div[id*=\"Jkf\"], div[id*=\"DrD\"]'); if (b) b.click(); }")

        # Wait 60 seconds with scrolling to keep session active
        dir_w = 1
        for sec in range(65, 0, -1):
            time.sleep(1.0)
            if sec % 10 == 0:
                print(f"  ⌛ Đang chờ máy chủ xác nhận thời gian on-site: còn {sec}s...")
                dir_w = -dir_w
                try: page_sponsor.mouse.wheel(0, 150 * dir_w)
                except Exception: pass

        print("[*] Hết thời gian chờ (60s+)! Mở modal xác thực QCaptcha...")
        page_sponsor.evaluate("() => { if (typeof window.__checkButtonClick === 'function') window.__checkButtonClick(4); }")

        try:
            frame_el = page_sponsor.wait_for_selector('iframe[src*="sslip.io"], iframe[src*="frame.html"]', timeout=30000)
            cf = frame_el.content_frame()
            cf.wait_for_selector('#box', timeout=30000)
            time.sleep(1)
            print("[*] Nhấn checkbox xác thực 'Tôi là con người'...")
            cf.click('#box', force=True)
        except Exception as e:
            print(f"[!] Warning waiting for frame/box: {e}")

        def get_qc_frame():
            for f in page_sponsor.frames:
                if any(k in f.url for k in ['sslip.io', 'frame.html']):
                    if not f.is_detached():
                        return f
            return None

        last_cid = None

        # Solve QCaptcha loop
        print("[*] Bắt đầu tự động giải QCaptcha challenge...")
        for round_idx in range(60):
            time.sleep(0.8)

            token = page_sponsor.evaluate('''() => {
                const api = window.hcaptcha || window.qcaptcha;
                return api && typeof api.getResponse === 'function' ? api.getResponse() : null;
            }''')
            if token:
                print(f"[🎉] QCaptcha Token Verified: {token[:40]}...")
                print("[*] Gửi token lên máy chủ lấy mã...")
                page_sponsor.evaluate('''([tok, key]) => {
                    let el = document.getElementById(key);
                    if (!el) {
                        const s = document.querySelector('script[src*="Traffic/Index"], script[src*="traffic/index"]');
                        if (s) {
                            const m = s.src.match(/[Tt]raffic\/[Ii]ndex\/([A-Za-z0-9_-]+)/);
                            if (m) el = document.getElementById(m[1]);
                        }
                    }
                    if (typeof window.__submitGetCode === 'function') {
                        window.__submitGetCode(el, '0', { qCaptchaToken: tok });
                    }
                    for (const b of document.querySelectorAll('#qcaptcha-modal-content button, button')) {
                        if (b.innerText.includes('Xác thực và lấy mã')) {
                            b.click();
                            break;
                        }
                    }
                }''', [token, traffic_key])
                break

            cur_cf = get_qc_frame()
            if not cur_cf:
                continue

            ch_info = cur_cf.evaluate('''() => {
                if (window.__qc_state && window.__qc_state.challenge) {
                    const ch = window.__qc_state.challenge;
                    return {
                        cid: ch.cid,
                        type: ch.type,
                        spec: ch.spec,
                        assets: (ch.assets || []).map(a => a.url)
                    };
                }
                return null;
            }''')

            if not ch_info:
                continue

            if ch_info['cid'] == last_cid:
                time.sleep(1.0)
                continue

            c_type = ch_info['type']
            assets = ch_info['assets']
            spec = ch_info['spec'] or {}
            q_text = (spec.get('questionKey') or spec.get('question', {}).get('vi', '') or '').lower()
            last_cid = ch_info['cid']
            print(f"[+] Nhận dạng Challenge: {c_type} ('{q_text}')")

            if c_type in ['grid3x3', 'oddoneout'] and 'chạm' not in q_text:
                args_list = [(i, u) for i, u in enumerate(assets)]
                features = list(executor.map(analyze_tile_url, args_list))
                features.sort(key=lambda x: x[0])

                target = []
                if 'khác nhóm' in q_text or 'khác' in q_text or c_type == 'oddoneout':
                    v_counts = [f[1] for f in features]
                    for i, v in enumerate(v_counts):
                        if v_counts.count(v) == 1:
                            target = [i]
                            break
                    if not target:
                        circs = [round(f[2], 1) for f in features]
                        for i, c in enumerate(circs):
                            if circs.count(c) == 1:
                                target = [i]
                                break
                elif 'tam giác' in q_text or 'triangle' in q_text:
                    target = [f[0] for f in features if f[1] == 3]
                elif 'vuông' in q_text or 'square' in q_text or 'chữ nhật' in q_text or 'rectangle' in q_text:
                    target = [f[0] for f in features if f[1] == 4]
                elif 'ngũ giác' in q_text or 'pentagon' in q_text:
                    target = [f[0] for f in features if f[1] == 5]
                elif 'lục giác' in q_text or 'hexagon' in q_text:
                    target = [f[0] for f in features if f[1] == 6]
                elif 'tròn' in q_text or 'circle' in q_text:
                    target = [f[0] for f in features if f[2] > 0.75]
                else:
                    v_counts = [f[1] for f in features]
                    for i, v in enumerate(v_counts):
                        if v_counts.count(v) == 1:
                            target = [i]
                            break

                if not target:
                    target = [0]

                print(f"   ➔ Đáp án chọn: {target}")
                cur_cf.evaluate('''(ans) => {
                    if (typeof window.__qc_submit === 'function') {
                        window.__qc_submit(ans);
                    }
                }''', target)
                time.sleep(0.6)

            elif c_type == 'order':
                args_list = [(i, u) for i, u in enumerate(assets)]
                features = list(executor.map(analyze_tile_url, args_list))
                features.sort(key=lambda x: x[0])
                direction = spec.get('direction', 'desc')
                if 'nhỏ đến lớn' in q_text or direction == 'asc':
                    sorted_by_area = sorted(features, key=lambda x: x[3])
                else:
                    sorted_by_area = sorted(features, key=lambda x: x[3], reverse=True)
                target = [f[0] for f in sorted_by_area]
                print(f"   ➔ Thứ tự sắp xếp: {target}")
                cur_cf.evaluate('''(ans) => {
                    if (typeof window.__qc_submit === 'function') {
                        window.__qc_submit(ans);
                    }
                }''', target)
                time.sleep(0.6)

            else:
                print(f"   ➔ Đổi dạng challenge ({c_type})...")
                cur_cf.evaluate('''() => {
                    if (typeof window.__qc_skip === 'function') {
                        window.__qc_skip();
                    }
                }''')
                time.sleep(0.4)

        # Wait for extracted code (turbo loop)
        for _ in range(25):
            if extracted_layma_code:
                break
            c_dom = page_sponsor.evaluate(f'''() => {{
                const el = document.getElementById('{traffic_key}');
                if (el) {{
                    const m = (el.innerText || '').match(/([A-Za-z0-9_\\-]{{4,20}})/);
                    if (m && !/lay|ma|click|link|sau|kiem/i.test(m[1])) return m[1];
                }}
                const cb = document.getElementById('trackingMessageContainer');
                if (cb) {{
                    const m = (cb.innerText || '').match(/([A-Za-z0-9_\\-]{{4,20}})/);
                    if (m && !/lay|ma|click|link|sau|kiem/i.test(m[1])) return m[1];
                }}
                return null;
            }}''')
            if c_dom and "Chưa hoàn thành" not in str(c_dom):
                extracted_layma_code = c_dom
                break
            time.sleep(0.25)

        if not extracted_layma_code:
            print("[!] Không lấy được mã LayMa. Kết thúc.")
            browser.close()
            return

        with open(CODE_FILE, "w", encoding="utf-8") as f_c:
            f_c.write(extracted_layma_code)

        # 3. Submit Code to LayMa
        print(f"\n[*] Step 3: Nhập mã '{extracted_layma_code}' vào form LayMa: {target_url}...")
        page_layma.bring_to_front()
        time.sleep(0.3)

        page_layma.evaluate('''(code) => {
            // Hook window.open to redirect immediately in same window
            window.open = function(u, target) {
                if (u && typeof u === 'string') {
                    window.location.href = u;
                }
                return null;
            };

            // Hook resolveCheckCodeRedirect to navigate immediately without waiting
            const oldResolve = window.resolveCheckCodeRedirect;
            window.resolveCheckCodeRedirect = function(res) {
                const u = oldResolve ? oldResolve(res) : (typeof res === 'string' ? res : (res && res.redirectUrl));
                if (u && typeof u === 'string') {
                    window.location.href = u;
                }
                return u;
            };

            const inp = document.getElementById('codeInput') || document.querySelector('input[name="code"]');
            if (inp) {
                inp.value = code;
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
            if (typeof redeemCode === 'function') {
                redeemCode();
            } else {
                const btn = document.getElementById('btn-xac-nhan') || document.querySelector('button[onclick*="submitCode"]');
                if (btn) btn.click();
            }
        }''', extracted_layma_code)
        print("✔ Đã gửi xác nhận mã trên LayMa!")

        # Wait for redirect to final destination url
        print("[*] Đang chờ trình duyệt chuyển hướng đến link đích cuối cùng...")
        for wait_i in range(80):
            if final_destination_url and "layma.net" not in final_destination_url and "/api/traffic/go/" not in final_destination_url:
                break

            curr = page_layma.url
            if curr and curr.startswith("http") and "layma.net" not in curr and "/api/traffic/go/" not in curr:
                final_destination_url = curr
                break

            time.sleep(0.5)

        # Fallback only if still on layma and direct_redirect_url was captured
        if (not final_destination_url or "layma.net" in final_destination_url) and direct_redirect_url:
            try:
                print(f"[*] Fallback: Điều hướng trực tiếp tới {direct_redirect_url}...")
                page_layma.goto(direct_redirect_url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                curr = page_layma.url
                if curr and "layma.net" not in curr and "/api/traffic/go/" not in curr:
                    final_destination_url = curr
            except Exception as e:
                print(f"[!] Fallback goto error: {e}")

        # Check DOM status if still on layma
        if not final_destination_url or "layma.net" in final_destination_url:
            print("[!] Đang kiểm tra DOM phản hồi của LayMa...")
            try:
                dom_status = page_layma.evaluate('''() => {
                    const th = document.getElementById('thongbao');
                    const cd = document.getElementById('countRedirect');
                    return {
                        thongbao: th ? th.innerText : null,
                        countRedirect: cd ? cd.innerText : null,
                        url: window.location.href
                    };
                }''')
                print(f"[!] DOM status: {dom_status}")
                if dom_status and dom_status.get('url') and "layma.net" not in dom_status['url'] and "/api/traffic/go/" not in dom_status['url']:
                    final_destination_url = dom_status['url']
            except Exception:
                pass

        # Final check of page_layma.url
        curr = page_layma.url
        if curr and curr.startswith("http") and "layma.net" not in curr and "/api/traffic/go/" not in curr:
            final_destination_url = curr

        if final_destination_url and "layma.net" not in final_destination_url and "/api/traffic/go/" not in final_destination_url:
            print("\n" + "=" * 70)
            print(f"🎉🎉🎉 FINAL DESTINATION URL: {final_destination_url}")
            print("=" * 70 + "\n")
            try:
                with open(DEST_FILE, "w", encoding="utf-8") as f_d:
                    f_d.write(final_destination_url.strip())
                with open(FINAL_DEST_FILE, "w", encoding="utf-8") as f_d:
                    f_d.write(final_destination_url.strip())
                desk_dest = os.path.expanduser(r"~\Desktop\destination_url.txt")
                with open(desk_dest, "w", encoding="utf-8") as f_d:
                    f_d.write(final_destination_url.strip())
            except Exception:
                pass
            copy_to_clipboard(final_destination_url)
            try:
                import winsound
                winsound.MessageBeep(-1)
            except Exception:
                pass
        else:
            print("[!] Không lấy được link đích cuối cùng.")

        time.sleep(2)
        browser.close()
        return final_destination_url

if __name__ == "__main__":
    run()
