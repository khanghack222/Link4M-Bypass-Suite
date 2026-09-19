import sys
import os
import subprocess

# Auto-detect and switch to Python 3.11 if current interpreter lacks playwright
try:
    import playwright
except ImportError:
    candidates = [
        r"C:\Users\XUAN\AppData\Local\Programs\Python\Python311\python.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python311\python.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python312\python.exe"),
        r"C:\Python311\python.exe",
        r"C:\Python312\python.exe"
    ]
    for p in candidates:
        if os.path.exists(p) and p != sys.executable:
            ret = subprocess.run([p] + sys.argv)
            sys.exit(ret.returncode)

import time
import json
import base64
import re
import shutil
import urllib.request
import urllib.parse
try:
    from patchright.sync_api import sync_playwright
    PATCHRIGHT_AVAILABLE = True
except ImportError:
    from playwright.sync_api import sync_playwright
    PATCHRIGHT_AVAILABLE = False
from rapidocr_onnxruntime import RapidOCR

# Cau hinh stdout UTF-8 cho terminal Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMP_DIR = os.path.join(ROOT_DIR, "data", "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
DEST_FILE = os.path.join(ROOT_DIR, "destination_url.txt")
CODE_FILE = os.path.join(ROOT_DIR, "extracted_code.txt")

ocr_engine = None

def get_ocr():
    global ocr_engine
    if ocr_engine is None:
        ocr_engine = RapidOCR()
    return ocr_engine

def clean_destination_url(url: str) -> str:
    if not url:
        return url
    if "bbmkts.com/go/file/" in url:
        encoded_part = url.split("/go/file/")[-1].split("?")[0].split("#")[0]
        # Thử unquote trước
        try:
            dec = urllib.parse.unquote(encoded_part)
            if dec.startswith("http"):
                return dec
        except Exception:
            pass
        # Thử base64
        try:
            dec = base64.b64decode(encoded_part + "===").decode("utf-8", errors="ignore")
            if dec.startswith("http"):
                return dec
        except Exception:
            pass
    return url

def run(target_link: str = None, headless: bool = None):
    if not target_link:
        target_link = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "https://bbmkts.com/go/3p82s"
    if headless is None:
        headless = False if ("--head" in sys.argv or "-w" in sys.argv or "--window" in sys.argv) else True

    # 0. Instant Zero-Click Base64 Decoder
    if "bbmkts.com/go/file/" in target_link:
        dec = clean_destination_url(target_link)
        if dec and dec.startswith("http") and "bbmkts.com/go/file/" not in dec:
            log(f"🎉 [ZERO-CLICK] Giai ma truc tiep tu link /go/file/: {dec}")
            with open(DEST_FILE, "w", encoding="utf-8") as f:
                f.write(dec)
            with open(os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), "w", encoding="utf-8") as f:
                f.write(dec)
            return dec

    final_destination = None

    with sync_playwright() as p:
        log("[1/4] Khoi dong trinh duyet Chromium...")
        from config import get_chrome_path
        c_path = get_chrome_path()
        
        ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'extensions', 'turnstile_patch'))
        user_data_dir = os.path.join(TEMP_DIR, "chrome_bbmkts_profile")
        if os.path.exists(user_data_dir):
            shutil.rmtree(user_data_dir, ignore_errors=True)

        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
        ]
        if os.path.exists(ext_dir):
            args.extend([
                f"--disable-extensions-except={ext_dir}",
                f"--load-extension={ext_dir}"
            ])

        # Headed is required for extension injection and Cloudflare Turnstile verification
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=c_path if c_path and os.path.exists(c_path) else None,
            headless=False,
            args=args,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        browser = context

        # Chan cac script tracker, chan incognito popup (KHONG duoc chan api.js vi can Cloudflare Turnstile)
        context.route("**/apiip.js*", lambda r: r.abort())
        context.route("**/sweetalert2*", lambda r: r.abort())
        context.route("**/firebase*", lambda r: r.abort())

        # TAB 1: KET NOI VA PHAN TICH TRANG BBMKTS
        page1 = context.pages[0] if context.pages else context.new_page()

        def handle_submit_response(resp):
            nonlocal final_destination
            if '/link/submit' in resp.url:
                try:
                    data = resp.json()
                    log(f"[API] Phan hoi /link/submit: {data}")
                    if 'url' in data and data['url']:
                        final_destination = clean_destination_url(data['url'])
                except Exception:
                    pass

        page1.on('response', handle_submit_response)

        # Vong lap thu nhiem vu (Toi da 3 lan thu/reroll)
        final_code = None
        turnstile_token = ""
        for attempt in range(1, 4):
            log(f"\n--- [LAN THU {attempt}/3] Load nhiem vu tai {target_link} ---")
            try:
                page1.goto(target_link, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                log(f"[TAB 1] Warning on load: {e}")

            time.sleep(2)
            html1 = page1.content()
            log(f"[TAB 1] Da tai DOM ({len(html1)} bytes).")

            # Cloudflare tren Playwright luon bi block -> Goi truc tiep Node.js Patchright Solver khong can kiem tra
            try:
                from turnstile_solver import get_turnstile_token
                sitekey = page1.evaluate("""() => {
                    let el = document.querySelector('.cf-turnstile') || document.querySelector('[data-sitekey]');
                    return el ? el.getAttribute('data-sitekey') : '0x4AAAAAAEzmJdRW__FHO9pu';
                }""") or "0x4AAAAAAEzmJdRW__FHO9pu"
                log(f"[TAB 1] Kich hoat truc tiep Turnstile Solver (Node.js Patchright)...")
                ts_res = get_turnstile_token(url="https://bbmkts.com", sitekey=sitekey, debug=False, headless=False)
                if ts_res.get('status') == 'success' and ts_res.get('turnstile_value'):
                    turnstile_token = ts_res['turnstile_value']
                    log(f"[TAB 1] Turnstile xac thuc thanh cong qua Patchright! Token len: {len(turnstile_token)}")
                    page1.evaluate("""(tok) => {
                        document.querySelectorAll('input[name="cf-turnstile-response"]').forEach(i => i.value = tok);
                    }""", turnstile_token)
            except Exception as e:
                log(f"[TAB 1] Warning Turnstile solver: {e}")

            final_code = None
            time.sleep(1)
            html1 = page1.content()

            # -------------------------------------------------------------
            # KIEM TRA CHIEN DICH LOAI B (CANVAS / MA TRUC TIEP / ANH STATIC / VUOT THANG)
            # -------------------------------------------------------------
            # 0. Kiem tra truc tiep noi dung van ban DOM (Chien dich Vuot Thang TrafficSEO "Khong phai cho")
            if any(k in html1.lower() for k in ['không phải chờ 200', 'không phải chờ', 'không phải code chờ giây', 'mã code theo hướng dẫn trong ảnh ở bước 4']):
                final_code = "trafficseo2025"
                log(f"[NHAN DIEN] Chien dich VUOT THANG tu van ban DOM Buoc 5! Ma mac dinh: >>> {final_code} <<<")

            img_u = None
            # 1. Tìm trực tiếp URL ảnh canvas hoặc ảnh hướng dẫn bước 4 qua evaluate trên page1
            try:
                img_u = page1.evaluate("""() => {
                    for (let s of document.querySelectorAll('script')) {
                        let txt = s.textContent || s.innerHTML || '';
                        if (txt.includes('imgCanvas') || txt.includes('canvas')) {
                            let m = txt.match(/['"](https?:\/\/[^'"]*uploads\/[^'"]+)['"]/);
                            if (!m) m = txt.match(/['"](\/uploads\/[^'"]+)['"]/);
                            if (m) return m[1];
                        }
                    }
                    let imgs = Array.from(document.querySelectorAll('img[src*="uploads/img_"]'));
                    for (let img of imgs) {
                        let src = img.getAttribute('src') || img.src;
                        if (src) return src;
                    }
                    return null;
                }""")
            except Exception:
                pass

            # 2. Fallback tìm qua regex trong html1
            if not img_u:
                for s in re.findall(r'<script[^>]*>(.*?)</script>', html1, re.S):
                    if 'imgCanvas' in s or 'canvas' in s:
                        m = re.search(r'[\'"](https?://[^\'"]*uploads/[^\'"]+)[\'"]', s)
                        if not m:
                            m = re.search(r'[\'"](/uploads/[^\'"]+)[\'"]', s)
                        if m:
                            img_u = m.group(1)
                            break
            if not img_u:
                all_step_imgs = re.findall(r'[\'"](https?://[^\'"]*uploads/img_[^\'"]+)[\'"]', html1)
                if all_step_imgs:
                    img_u = all_step_imgs[-1]

            if not final_code and img_u:
                if not img_u.startswith('http'):
                    img_u = 'https://bbmkts.com' + img_u
                
                log(f"[TAB 1] Phat hien anh huong dan/Canvas truc tiep tu server: {img_u}")
                tmp_img = os.path.join(TEMP_DIR, "canvas_test.png")
                try:
                    urllib.request.urlretrieve(img_u, tmp_img)
                    from PIL import Image
                    im = Image.open(tmp_img)
                    lines, _ = get_ocr()(tmp_img)
                    all_text = ' '.join([l[1] for l in (lines or [])])
                    log(f"[OCR CANVAS] {all_text}")

                    # 1. Bóc tách chiến dịch Vượt thẳng TrafficSEO ("Tra...25" / "Hệ thống SEO" / "không phải code chờ giây")
                    if ('Tra' in all_text and '25' in all_text) or any(k in all_text.lower() for k in ['trafficseo', 'he thong seo', 'khong phai code cho giay', 'khong phai ma cho giay', 'o mau vang']) or any(k in html1.lower() for k in ['không phải chờ', 'không phải code chờ giây']):
                        m_yr = re.search(r'Tra[^\d]*(\d{2,4})', all_text, re.I)
                        if m_yr:
                            yr = m_yr.group(1)
                            if len(yr) == 2: yr = '20' + yr
                            final_code = f"trafficseo{yr}"
                        else:
                            final_code = "trafficseo2025"
                        log(f"[NHAN DIEN] Chien dich VUOT THANG (TrafficSEO)! Ma: >>> {final_code} <<<")

                    # 2. Bóc tách MST / Mã số thuế / Code từ all_text
                    if not final_code:
                        m_mst = re.search(r'(?:MST|MÃ\s*SỐ\s*THUẾ|MÃ|CODE)[:\s]*([0-9A-Za-z]+)', all_text, re.I)
                        if m_mst and len(m_mst.group(1).strip()) >= 5:
                            cand = m_mst.group(1).strip()
                            if cand.lower() not in ['code', 'nhap', 'dung', 'sai']:
                                final_code = cand.lower()
                                log(f"[NHAN DIEN] Chien dich Co san ma tren anh (MST/Code)! Ma: >>> {final_code} <<<")

                    # 3. Bóc tách chuỗi số 8-14 ký tự (ví dụ: mã số thuế 0311949753)
                    if not final_code:
                        m_num = re.search(r'\b\d{8,14}\b', all_text)
                        if m_num:
                            final_code = m_num.group(0).strip()
                            log(f"[NHAN DIEN] Chien dich Co san ma tren anh (Chuoi so MST)! Ma: >>> {final_code} <<<")

                    # 4. Bóc tách theo bounding box của từng dòng
                    if not final_code and lines:
                        for l in lines:
                            txt_raw = l[1].strip()
                            m_sub = re.search(r'(?:MST[:\s]*)?([0-9]{8,12})', txt_raw, re.I)
                            if m_sub:
                                final_code = m_sub.group(1).strip()
                                log(f"[NHAN DIEN] Phat hien ma tu dong OCR: >>> {final_code} <<<")
                                break

                    # 5. Fallback code_cand
                    if not final_code and im.size[0] < 500 and im.size[1] < 150:
                        if lines:
                            sorted_lines = sorted(lines, key=lambda x: x[0][0][0])
                            code_cand = re.sub(r'[^0-9a-zA-Z]', '', ''.join([l[1] for l in sorted_lines]))
                            code_cand = re.sub(r'^MST', '', code_cand, flags=re.I)
                            if 5 <= len(code_cand) <= 15:
                                final_code = code_cand.lower()
                                log(f"[NHAN DIEN] Chien dich Co san ma tren anh (Fallback)! Ma: >>> {final_code} <<<")
                except Exception as e:
                    log(f"[WARN] Loi xu ly anh canvas: {e}")

            # -------------------------------------------------------------
            # KIEM TRA CHIEN DICH LOAI A (LINK NGOAI / WEBSITE DOI TAC)
            # -------------------------------------------------------------
            if not final_code:
                log("[NHAN DIEN] Chien dich Website Doi tac ngoai (Countdown Button)!")
                
                # Tim anh huong dan Buoc 3
                guide_url = "https://bbmkts.com/uploads/img_6a9a2b1a162aa2_23092712.jpg"
                m_guide = re.search(r'Bước\s*3:.*?<img[^>]+src=[\'"]([^\'"]+uploads/[^\'"]+)[\'"]', html1, re.S | re.I)
                if m_guide:
                    u = m_guide.group(1)
                    guide_url = u if u.startswith('http') else 'https://bbmkts.com/' + u.lstrip('/')
                else:
                    all_imgs = re.findall(r'https?://bbmkts\.com/uploads/img_[^"\'\s>]+', html1)
                    if all_imgs:
                        guide_url = all_imgs[0]

                log(f"[TAB 1] Anh huong dan tim trang: {guide_url}")
                tmp_guide = os.path.join(TEMP_DIR, "guide_step3.jpg")
                try:
                    urllib.request.urlretrieve(guide_url, tmp_guide)
                except Exception:
                    pass

                target_url = None

                # 1. Kiem tra window.taskConfig
                try:
                    req_domains = page1.evaluate("() => window.taskConfig && window.taskConfig.requiredDomains ? window.taskConfig.requiredDomains : null")
                    if req_domains and len(req_domains) > 0:
                        target_url = f"https://{req_domains[0]}/"
                        log(f"[CONFIG] Phat hien requiredDomains tu taskConfig: {target_url}")
                except Exception:
                    pass

                # 1.5. Priority 0: Trích xuất domain qua Cloud OCR API
                if not target_url and guide_url:
                    try:
                        from captcha_api_client import resolve_domain_ocr
                        doms = resolve_domain_ocr(image_url=guide_url)
                        if doms:
                            for d in doms:
                                if not any(k in d.lower() for k in ['google', 'youtube', 'facebook', 'bbmkts', 'imgur']):
                                    target_url = f"https://{d.strip('/')}/"
                                    log(f"[Cloud API OCR] Đã trích xuất domain nhà tài trợ: {target_url}")
                                    break
                    except Exception as e:
                        log(f"[Cloud API OCR] Fallback sang OCR local: {e}")

                # 2. Phat hien Red Bounding Box
                if not target_url:
                    try:
                        from PIL import Image
                        import numpy as np
                        im_guide = Image.open(tmp_guide).convert('RGB')
                        arr = np.array(im_guide)
                        red_mask = (arr[:, :, 0] > 180) & (arr[:, :, 1] < 60) & (arr[:, :, 2] < 60)
                        y_indices, x_indices = np.where(red_mask)
                        h_threshold = int(arr.shape[0] * 0.3)
                        mask_lower = y_indices > h_threshold
                        y_low = y_indices[mask_lower]
                        x_low = x_indices[mask_lower]
                        if len(y_low) > 0:
                            min_y, max_y = y_low.min(), y_low.max()
                            min_x, max_x = x_low.min(), x_low.max()
                            crop_im = im_guide.crop((min_x, min_y, max_x, max_y))
                            tmp_crop = os.path.join(TEMP_DIR, "crop_target.jpg")
                            crop_im.save(tmp_crop)
                            lines_crop, _ = get_ocr()(tmp_crop)
                            texts_crop = [l[1] for l in (lines_crop or [])]
                            log(f"[OCR RED BOX] {' | '.join(texts_crop)}")
                            for t in texts_crop:
                                m_u = re.search(r'https?://([a-zA-Z0-9.-]+\.(?:com|vn|net|org|edu|gov))[>/]([a-zA-Z0-9._/-]+)', t)
                                if m_u:
                                    dom = m_u.group(1).lower().strip('.')
                                    if not any(k in dom for k in ['google', 'youtube', 'facebook', 'bbmkts', 'imgur', 'aimos']):
                                        slug = m_u.group(2).strip('/')
                                        target_url = f"https://{dom}/{slug}/"
                                        break
                            if not target_url:
                                for t in texts_crop:
                                    m_d = re.search(r'https?://([a-zA-Z0-9.-]+\.(?:com|vn|net|org|edu|gov))', t) or re.search(r'([a-zA-Z0-9.-]+\.(?:com|vn|net|org|edu|gov))', t)
                                    if m_d:
                                        dom = m_d.group(1).lower().strip('.')
                                        if not any(k in dom for k in ['google', 'youtube', 'facebook', 'bbmkts', 'imgur', 'aimos']):
                                            target_url = f"https://{dom}/"
                                            break
                    except Exception as e:
                        log(f"[WARN] Loi red-box detection: {e}")

                # 3. Fallback OCR full anh
                if not target_url:
                    try:
                        lines, _ = get_ocr()(tmp_guide)
                        texts = [l[1] for l in (lines or [])]
                        for t in texts:
                            m_u = re.search(r'https?://([a-zA-Z0-9.-]+\.(?:com|vn|net|org|edu|gov))[>/]([a-zA-Z0-9._/-]+)', t)
                            if m_u:
                                dom = m_u.group(1).lower().strip('.')
                                if not any(k in dom for k in ['google', 'youtube', 'facebook', 'bbmkts', 'imgur', 'aimos']):
                                    slug = m_u.group(2).strip('./')
                                    if slug:
                                        target_url = f"https://{dom}/{slug}/"
                                    else:
                                        target_url = f"https://{dom}/"
                                    break
                        if not target_url:
                            for t in texts:
                                m_d = re.search(r'https?://([a-zA-Z0-9.-]+\.(?:com|vn|net|org|edu|gov))', t) or re.search(r'([a-zA-Z0-9.-]+\.(?:com|vn|net|org|edu|gov))', t)
                                if m_d:
                                    dom = m_d.group(1).lower().strip('.')
                                    if not any(k in dom for k in ['google', 'youtube', 'facebook', 'bbmkts', 'imgur', 'aimos']):
                                        target_url = f"https://{dom}/"
                                        break
                    except Exception:
                        pass

                # Bang map chinh xac cac landing page co dinh
                if target_url:
                    if 'luxbikes.vn' in target_url and target_url.rstrip('/') == 'https://luxbikes.vn':
                        target_url = 'https://luxbikes.vn/xe-dap-tro-luc/'
                    elif 'grandpalace.com.vn' in target_url and target_url.rstrip('/') == 'https://grandpalace.com.vn':
                        target_url = 'https://grandpalace.com.vn/dich-vu/tiec-cuoi-tron-goi/'
                    elif 'namvietlift.com' in target_url and target_url.rstrip('/') == 'https://namvietlift.com':
                        target_url = 'https://namvietlift.com/xe-nang-tay/'
                    elif 'truongmaisaigon.vn' in target_url and target_url.rstrip('/') == 'https://truongmaisaigon.vn':
                        target_url = 'https://truongmaisaigon.vn/ghe-xoay-van-phong/'
                    elif 'eterra.vn' in target_url and target_url.rstrip('/') == 'https://eterra.vn':
                        target_url = 'https://eterra.vn/tu-chau-lavabo-eterra/'

                all_t = ' '.join(texts_crop if 'texts_crop' in locals() else (texts if 'texts' in locals() else [])).lower()
                if not target_url:
                    if 'grandpalace' in all_t or 'grand palace' in all_t:
                        target_url = 'https://grandpalace.com.vn/dich-vu/tiec-cuoi-tron-goi/'
                    elif 'eterra' in all_t:
                        target_url = 'https://eterra.vn/tu-chau-lavabo-eterra/'
                    elif 'bulong' in all_t or 'hoangha' in all_t:
                        target_url = 'https://bulonghoangha.com/'
                    elif 'truongmai' in all_t:
                        target_url = 'https://truongmaisaigon.vn/ghe-xoay-van-phong/'
                    elif 'namviet' in all_t:
                        target_url = 'https://namvietlift.com/xe-nang-tay/'
                    elif 'luxbike' in all_t:
                        target_url = 'https://luxbikes.vn/xe-dap-tro-luc/'

                if not target_url:
                    target_url = "https://luxbikes.vn/xe-dap-tro-luc/"

                log(f"[TARGET] Website doi tac duoc xac dinh: {target_url}")

                # ---------------------------------------------------------
                # TAB 2: TRUY CAP WEB NGOAI VA DEM NGUOC
                # ---------------------------------------------------------
                log(f"[2/4] [TAB 2] Mo tab moi truy cap {target_url} ...")
                page2 = context.new_page()

                abx_code = None
                def handle_abx(resp):
                    nonlocal abx_code
                    if any(k in resp.url for k in ['00abx', '02abx', '03abx']):
                        try:
                            data = resp.json()
                            tok = data.get('token')
                            if tok:
                                dec = json.loads(base64.b64decode(tok.split('.')[0] + '===').decode('utf-8'))
                                abx_code = dec.get('code')
                                log(f"[API {resp.url.split('?')[0].split('/')[-1]}] Server tra ve ma goc: >>> {abx_code} <<<")
                        except Exception:
                            pass

                page2.on('response', handle_abx)

                # Patch script bb*.js
                def route_bb(route):
                    url = route.request.url
                    resp = route.fetch()
                    txt = resp.text()
                    if 'bb' in url:
                        txt = "function detectIncognito(){ return Promise.resolve({isPrivate: false}); }\n" + txt
                        txt = txt.replace('if(_0x13d311[', 'if(false&&_0x13d311[')
                        txt = txt.replace('function checkAdsClick(){', 'function checkAdsClick(){return false;')
                        log(f"[PATCH] Da bypass Incognito tren script {url.split('?')[0].split('/')[-1]}!")
                    route.fulfill(response=resp, body=txt)

                page2.route(re.compile(r'bbmkts\.com/js/bb.*'), route_bb)

                page2.add_init_script("""
                    Object.defineProperty(document, 'referrer', { get: () => 'https://www.google.com/', configurable: true });
                    Document.prototype.hasFocus = () => true;
                    document.hasFocus = () => true;
                    window.hasFocus = () => true;
                    Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
                    Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
                    window.detectIncognito = async () => ({ isPrivate: false, browserName: 'Chrome' });
                """)

                try:
                    page2.goto(target_url, referer="https://www.google.com/", wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    log(f"[TAB 2] Warning on load: {e}")

                time.sleep(3)
                log("[TAB 2] Cuon trang de tim nut lay ma...")
                page2.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                # Tim nut voi danh sach selector da dang
                bb = None
                selectors = [
                    '#bb', '#bb1', '#bb2', '#00xoo', '.btn-layma',
                    'button:has-text("LẤY MÃ")', 'a:has-text("LẤY MÃ")',
                    '[id*="layma"]', '[class*="layma"]'
                ]
                for sel in selectors:
                    try:
                        el = page2.query_selector(sel)
                        if el and el.is_visible():
                            bb = el
                            log(f"[TAB 2] Tim thay button lay ma qua selector: '{sel}'")
                            break
                    except Exception:
                        pass

                if not bb:
                    log("[!] Khong tim thay button lay ma tren web doi tac nay!")
                    page2.close()
                    log("[RETRY] Kich hoat 'Doi tu khoa moi' tren Tab 1 de lay nhiem vu khac...")
                    page1.bring_to_front()
                    page1.evaluate("if (typeof confirmReload === 'function') confirmReload(); else location.reload();")
                    time.sleep(4)
                    continue

                # Click button bat dau countdown
                log("[TAB 2] Click button bat dau dem nguoc...")
                bb.scroll_into_view_if_needed()
                time.sleep(1)
                try:
                    bb.click()
                except Exception:
                    pass

                for i in range(95):
                    time.sleep(1)

                    try:
                        txt = bb.inner_text().strip().replace('\n', ' ')
                    except Exception:
                        txt = ""
                    txt_upper = txt.upper()

                    if i % 10 == 0 or not any(k in txt_upper for k in ['ĐỢI', 'CHỜ', 'SAU', 'S']):
                        log(f"  [Countdown {i}s] Trang thai nut: '{txt}'")

                    # Neu timer da hoan tat (khong con text dem nguoc)
                    is_counting = any(k in txt_upper for k in ['ĐỢI', 'CHỜ', 'SAU', 'GIÂY']) or bool(re.search(r'\b\d+s\b', txt, re.I))
                    if abx_code and not is_counting and i >= 30:
                        final_code = abx_code
                        log(f"\n==================================================")
                        log(f"   [TAB 2] DA HOAN TAT DEM NGUOC VA LAY MA: >>> {final_code} <<<")
                        log(f"==================================================\n")
                        break

                    # Kiem tra ngay trong DOM page2 xem co chua script TrafficSEO khong
                    if not final_code:
                        try:
                            cand_dom = page2.evaluate("""() => {
                                for (let s of document.querySelectorAll('script')) {
                                    let m = (s.textContent || s.innerHTML || '').match(/TrafficSEO\\d*/i);
                                    if (m) return m[0].toLowerCase();
                                }
                                return null;
                            }""")
                            if cand_dom:
                                final_code = cand_dom
                                log(f"\n==================================================")
                                log(f"   [TAB 2] PHAT HIEN MA TRUC TIEP TRONG DOM: >>> {final_code} <<<")
                                log(f"==================================================\n")
                                break
                        except Exception:
                            pass

                    # Kiem tra xem tren button co xuat hien ma code ngay lap tuc khong (Chien dich vuot thang)
                    m_seo = re.search(r'(?:Hệ\s*thống\s*SEO|TrafficSEO)\s*([A-Za-z0-9_]+)', txt, re.I)
                    if m_seo:
                        final_code = m_seo.group(1).strip().lower()
                        log(f"\n==================================================")
                        log(f"   [TAB 2] DA LAY DUOC MA SEO TRUC TIEP TREN NUT (0s): >>> {final_code} <<<")
                        log(f"==================================================\n")
                        break

                    m_btn_code = re.search(r'\b[A-Za-z0-9]{6,15}\b', txt)
                    if m_btn_code:
                        cand = m_btn_code.group(0).strip()
                        if cand.upper() not in ['HETHONG', 'HETHONGSEO', 'KHONGPHAI', 'TRONGO', 'BUTTON', 'SUBMIT'] and not (cand.isdigit() and len(cand) <= 3):
                            if len(cand) >= 8 or (any(c.isalpha() for c in cand) and any(c.isdigit() for c in cand)):
                                final_code = cand.lower()
                                log(f"\n==================================================")
                                log(f"   [TAB 2] DA LAY DUOC MA TRUC TIEP TREN NUT (0s): >>> {final_code} <<<")
                                log(f"==================================================\n")
                                break

                    # Neu nut chua dem nguoc sau vai giay, kich hoat click truc tiep
                    if i in [3, 6, 9] and txt.strip() == 'LẤY MÃ':
                        try:
                            bb.evaluate("el => { el.click(); el.dispatchEvent(new MouseEvent('click', {bubbles: true})); }")
                        except Exception:
                            pass

                    # Neu sau 15s nut van giu nguyen chu 'LAY MA' (khong he thay doi text), moi thoat
                    if i >= 15 and not abx_code and txt.strip() == 'LẤY MÃ' and not any(k in txt_upper for k in ['ĐỢI', 'CHỜ', 'SAU', 'S', 'GIÂY']):
                        log("[TAB 2] Button khong dem nguoc tren web nay, chuyen sang thu web khac...")
                        break

                    # Kiem tra neu trang doi tac yeu cau chuyen sang Buoc 2 (2-in-1)
                    if 'Nhấn vào đây' in txt or 'tiếp tục' in txt:
                        link2 = page2.query_selector('a[href*="traffic="]') or bb.query_selector('a')
                        if link2:
                            next_u = link2.get_attribute('href')
                            log(f"[TAB 2] Chuyen tiep sang trang Buoc 2: {next_u}")
                            page2.goto(next_u, referer=page2.url, wait_until="domcontentloaded")
                            time.sleep(3)
                            page2.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(2)
                            for sel in selectors:
                                try:
                                    el = page2.query_selector(sel)
                                    if el and el.is_visible():
                                        bb = el
                                        bb.click()
                                        log("[TAB 2] Da click nut Buoc 2/2 thanh cong!")
                                        break
                                except Exception:
                                    pass
                            continue

                    # Kiem tra ma tren button
                    if not any(k in txt_upper for k in ['ĐỢI', 'CHỜ', 'SAU', 'S', 'GIÂY']) and txt.strip() != 'LẤY MÃ' and len(txt) >= 4:
                        final_code = txt
                        log(f"\n==================================================")
                        log(f"   [TAB 2] DA LAY DUOC MA THANH CONG: >>> {final_code} <<<")
                        log(f"==================================================\n")
                        break

                page2.close()

            # Neu da lay duoc ma, thoat khoi vong lap thu
            if final_code:
                break

        if not final_code:
            log("[-] Khong the lay duoc ma xac nhan sau cac lan thu!")
            browser.close()
            return None

        # -------------------------------------------------------------
        # TAB 1: NHAP MA VA SUBMIT
        # -------------------------------------------------------------
        log(f"[3/4] [TAB 1] Quay lai trang BBMKTS de mo khoa va nhap ma...")
        page1.bring_to_front()

        # Kich hoat click gia lap link quang cao ma khong mo popup ngoai y muon
        try:
            page1.evaluate("""() => {
                let l = document.getElementById('link');
                if (l) {
                    l.removeAttribute('target');
                    l.removeAttribute('href');
                    l.click();
                }
            }""")
        except Exception:
            pass
        time.sleep(1)

        inp = page1.query_selector('#input-field') or page1.query_selector('input[name="code"]')
        if inp:
            log(f"[TAB 1] Dien ma '{final_code}' vao o nhap lieu...")
            inp.fill(final_code)
            inp.dispatch_event("input")
            inp.dispatch_event("change")

        # -------------------------------------------------------------
        # CLOUDFLARE TURNSTILE TOKEN SYNC & VERIFY
        # -------------------------------------------------------------
        # Dong bo token Turnstile da lay tu Buoc 1
        if not turnstile_token or len(turnstile_token) < 20:
            log("[TAB 1] Kich hoat Turnstile Solver doc lap (Node.js Patchright)...")
            try:
                from turnstile_solver import get_turnstile_token
                sitekey = page1.evaluate("""() => {
                    let el = document.querySelector('.cf-turnstile') || document.querySelector('[data-sitekey]');
                    return el ? el.getAttribute('data-sitekey') : '0x4AAAAAAEzmJdRW__FHO9pu';
                }""") or "0x4AAAAAAEzmJdRW__FHO9pu"
                ts_res = get_turnstile_token(url="https://bbmkts.com", sitekey=sitekey, debug=False, headless=False)
                if ts_res.get('status') == 'success' and ts_res.get('turnstile_value'):
                    turnstile_token = ts_res['turnstile_value']
                    log(f"[TAB 1] Turnstile Solver thanh cong! Token len: {len(turnstile_token)}")
            except Exception as e:
                log(f"[TAB 1] Warning Turnstile solver: {e}")
            except Exception as e:
                log(f"[TAB 1] Warning Turnstile Solver fallback: {e}")

        cf_solved_token = turnstile_token or ""
        # Dong bo token da lay vao toan bo cac the input cf-turnstile-response tren DOM
        if cf_solved_token:
            page1.evaluate("""(tok) => {
                document.querySelectorAll('input[name="cf-turnstile-response"]').forEach(i => {
                    i.value = tok;
                });
                let btn = document.getElementById('formgetlink');
                if (btn) {
                    btn.disabled = false;
                }
            }""", cf_solved_token)

        time.sleep(1)

        final_code = final_code.strip().lower()
        log(f"[TAB 1] Gui request submit ma '{final_code}' truc tiep qua fetch...")
        res = page1.evaluate("""async ({code, forcedToken}) => {
            let token = '';
            let type = '';
            let tokenInp = document.querySelector('input[name="token"]');
            if (tokenInp) token = tokenInp.value;
            
            let scripts = Array.from(document.querySelectorAll('script')).map(s => s.textContent || s.innerHTML || '');
            for (let s of scripts) {
                let m = s.match(/token:\\s*['"]([A-Za-z0-9._=-]+)['"]/);
                if (m) {
                    token = m[1];
                    if (s.includes("type: 'available'")) type = 'available';
                    break;
                }
            }

            // Điền trực tiếp vào ô input trên giao diện DOM
            let codeInp = document.querySelector('input[name="code"]');
            if (codeInp) {
                codeInp.value = code;
                codeInp.dispatchEvent(new Event('input', { bubbles: true }));
                codeInp.dispatchEvent(new Event('change', { bubbles: true }));
            }

            let fm = document.getElementById('fm');
            let sendCode = async (c) => {
                let body = new URLSearchParams();
                body.append('code', c.trim().toLowerCase());
                if (token) body.append('token', token);
                if (type) body.append('type', type);
                if (fm) {
                    for (let el of fm.elements) {
                        if (el.name && el.name !== 'code' && !body.has(el.name)) {
                            body.append(el.name, el.value);
                        }
                    }
                }
                
                let cfToken = forcedToken || '';
                if (!cfToken) {
                    try {
                        if (typeof turnstile !== 'undefined' && turnstile.getResponse) {
                            cfToken = turnstile.getResponse() || '';
                        }
                    } catch(e) {}
                }
                if (!cfToken) {
                    let cfInputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
                    for (let inp of cfInputs) {
                        if (inp.value) { cfToken = inp.value; break; }
                    }
                }
                if (cfToken) {
                    body.set('cf-turnstile-response', cfToken);
                }

                let r = await fetch('https://bbmkts.com/link/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: body.toString()
                });
                let json = await r.json();
                return { ok: true, data: json, status: r.status };
            };

            try {
                let res = await sendCode(code);
                return res;
            } catch (e) {
                return { ok: false, error: e.toString() };
            }
        }""", {"code": final_code, "forcedToken": cf_solved_token})
        log(f"[TAB 1] Ket qua submit: {res}")
        if res and res.get('ok') and isinstance(res.get('data'), dict) and res['data'].get('url'):
            final_destination = res['data']['url']
            log(f"[TAB 1] Phat hien link dich tu API: {final_destination}")
        elif res and res.get('ok') and isinstance(res.get('data'), str) and res['data'].startswith('http'):
            final_destination = res['data']
            log(f"[TAB 1] Phat hien link dich: {final_destination}")
        else:
            check_btn = page1.query_selector('#formgetlink') or page1.query_selector('#check222') or page1.query_selector('button[type="submit"]')
            if check_btn:
                log("[TAB 1] Mo khoa va click nut submit (#formgetlink / #check222)...")
                page1.evaluate("""() => {
                    let b = document.getElementById('formgetlink') || document.getElementById('check222') || document.querySelector('button[type="submit"]');
                    if (b) { b.disabled = false; b.click(); }
                }""")

        # -------------------------------------------------------------
        # TRICH XUAT VA GIAI MA LINK NGOAI CUOI CUNG
        # -------------------------------------------------------------
        log("[4/4] Dang cho nhan link chuyen huong dich...")
        for sec in range(25):
            if final_destination:
                break
            try:
                cur = page1.url
                if 'bbmkts.com/go/' not in cur and 'about:blank' not in cur:
                    final_destination = cur
                    break
            except Exception:
                pass

            try:
                toast = page1.query_selector('.toast-message')
                if toast and toast.is_visible():
                    log(f"  [Toast message] {toast.inner_text()}")
            except Exception:
                pass
            time.sleep(1)

        time.sleep(2)
        try:
            cur = page1.url
            if 'bbmkts.com/go/' not in cur and 'about:blank' not in cur:
                final_destination = cur
        except Exception:
            pass

        # Bypas trang trung gian /go/file/ de trich xuat link ngoai thuc te
        if final_destination:
            final_destination = clean_destination_url(final_destination)
            if 'bbmkts.com/go/file/' not in final_destination:
                log(f"[GET LINK NGOAI] Da giai ma URL dich goc tu trang file: {final_destination}")

        log("=================================================================")
        if final_destination:
            log(f"   [THANH CONG 100%] LINK DICH CUOI CUNG:")
            log(f"   >>> {final_destination} <<<")
            log(f"FINAL DESTINATION URL: {final_destination}")
        else:
            log(f"   [-] URL hien tai: {page1.url}")
        log("=================================================================")

        # Chup anh man hinh ket qua
        screen_path = os.path.join(ROOT_DIR, "final_destination_screen.png")
        try:
            page1.screenshot(path=screen_path)
            log(f"[+] Da chup anh man hinh ket qua luu tai: {screen_path}")
        except Exception:
            pass

        browser.close()
        
        if final_destination:
            try:
                with open(DEST_FILE, "w", encoding="utf-8") as f:
                    f.write(final_destination)
                final_dest_file = os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt")
                with open(final_dest_file, "w", encoding="utf-8") as f:
                    f.write(final_destination)
                desk_dest = os.path.expanduser(r"~\Desktop\destination_url.txt")
                with open(desk_dest, "w", encoding="utf-8") as f_d:
                    f_d.write(final_destination)
            except Exception:
                pass
            try:
                if sys.platform == "win32":
                    import subprocess
                    subprocess.run(["clip"], input=final_destination.encode("utf-8"), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        log("=== BYPASS HOAN TAT 100% ===")
        return final_destination

if __name__ == "__main__":
    run()
