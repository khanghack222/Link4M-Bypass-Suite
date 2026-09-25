import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Tu dong chuyen sang Python 3.11 neu dang chay o Python khac ma thieu thu vien
PYTHON_311 = r"C:\Users\XUAN\AppData\Local\Programs\Python\Python311\python.exe"
if os.path.exists(PYTHON_311) and sys.executable.lower() != PYTHON_311.lower():
    import subprocess
    cmd = [PYTHON_311] + sys.argv
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

import time
import shutil
import json
import re
import urllib.request
import urllib.parse
import uuid
try:
    from patchright.sync_api import sync_playwright
    IS_PATCHRIGHT = True
except ImportError:
    from playwright.sync_api import sync_playwright
    IS_PATCHRIGHT = False

from config import CHROME_PATH, ROOT_DIR, DEST_FILE, CODE_FILE, log, copy_to_clipboard, load_proxies

ROTATE_PROXY_URL = "https://pandaproxys.com/api/v3/users/rotatev2?token=MTc5MDM1Njk0OTI5OTtrYWxlYmhlbmxleTgyNTM7YXBpLXByb3h5LTIuaG9tZXByb3h5LnZu_40b52b9661a3c1307bbebc46ddc1ab7f82fc01a4"

def rotate_proxy():
    try:
        req = urllib.request.Request(ROTATE_PROXY_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
            log(f"[+] Proxy rotated: {data.get('message')} | IP: {data.get('ip')}")
            return data
    except Exception as e:
        log(f"[!] Proxy rotation note: {e}")
        return None
from sponsor import get_ocr, extract_domain_candidates, probe_domain_live, resolve_ip_google

def is_valid_destination(u: str, sponsor_domain: str = None) -> bool:
    if not u or not isinstance(u, str) or not u.startswith("http"):
        return False
    u_low = u.lower()
    ignored = [
        "domain.com", "example.com",
        "gtraffic.io", "client.gtraffic.io", "dr-client.gtraffic.io", "direct.gtraffic.io",
        "cdn.gtraffic.io", "about:blank", "google.com/recaptcha", "gstatic.com/recaptcha",
        "doubleclick.net", "googlesyndication", "googleadservices", "adservice.google",
        "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com", "telegram.org",
        "t.me", "linkedin.com", "tiktok.com", "youtube.com", "zalo.me",
        # Ad networks & popups
        "quynhorange.com", "shopee.vn", "lazada.vn", "tiki.vn", "s.shopee.vn", "c.lazada.vn",
        "adsterra", "propellerads", "popads", "onclickads", "adcash", "exoclick",
        "histats.com", "cloudflare.com", "challenges.cloudflare.com", "traffic.pages.dev"
    ]
    if any(d in u_low for d in ignored):
        return False
    # Filter marketing/tracking query parameters that indicate affiliate redirect
    if any(p in u_low for p in ["utm_campaign=direct-funnels", "utm_source=quynhorange", "utm_content=gifts"]):
        return False
    if sponsor_domain:
        try:
            s_host = urllib.parse.urlparse(sponsor_domain).netloc.lower()
            u_host = urllib.parse.urlparse(u).netloc.lower()
            if s_host and (s_host in u_host or u_host in s_host):
                return False
        except Exception:
            pass
    return True

CAMPAIGN_RULES = [
    (['bong da', 'bóng đá', 'bongda', 'ca cuoc', 'cá cược', 'ca do', 'cá độ', '686', 'nutscredit', 'cugcbong', 'cuocbong'], ['https://bongda686.in.net', 'https://nutscredit.com', 'https://bongda686.com']),
    (['ki tu', 'kí tự', 'kitu', '360', 'dac biet', 'đặc biệt'], ['https://kitu360.com']),
    (['phan van', 'phan văn', 'phanvan', 'santos'], ['https://phanvansantos.com']),
    (['sunwin', 'sun win', 'sun', 'urano', 'waygo', 'sixtyseven'], ['https://urano.com.co', 'https://waygo.com.co', 'https://sunwin.sixtyseven.co.in']),
    (['w88', 'w 88', 'ananta', 'anantafarming'], ['https://anantafarming.in.net', 'https://anantafarming.com']),
    (['fun', 'fun88', 'greenco', 'intermarket', 'inter', 'inte', 'linkvaofun88'], ['https://intermarket.com.co', 'https://greenco.com.co']),
    (['hitclub', 'hit club', 'stridewalk', 'stride'], ['https://hitclub.stridewalk.in', 'https://stridewalk.in']),
    (['qh88', 'qh 88', 'qmmnews', 'qmm'], ['https://qmmnews.in.net']),
    (['ok365', 'ok 365'], ['https://ok365.com']),
    (['mu88', 'mu 88', 'antena', 'antenacat', 'antenacata', 'catalana'], ['https://antenacatalana.net']),
    (['van phong', 'văn phòng', 'hai ba trung', 'hai bà trưng', 'tim van phong', 'cho thue van phong', 'timvanphong'], ['https://timvanphong.com.vn']),
    (['thoitiet', 'thời tiết', 'thoitiethomnay'], ['https://thoitiethomnay.org']),
    (['eric ly', 'ericly'], ['https://ericly.net']),
    (['188 bet', '188bet', 'bet188', 'bet 188', 'agobet'], ['https://agobet.cc']),
    (['incafe', 'in cafe', 'cafe'], ['https://incafe.com.co']),
]

def resolve_sponsor_domain(keyword_text: str, img_url: str, opener=None) -> str:
    import unicodedata
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def fetch_url(req, timeout=4.0):
        try:
            return urllib.request.urlopen(req, context=ctx, timeout=timeout)
        except Exception:
            if opener:
                try:
                    return opener.open(req, timeout=timeout)
                except Exception:
                    pass
            raise

    def generate_slug_variants(text: str) -> list:
        nfkd = unicodedata.normalize('NFKD', text or '')
        ascii_t = ''.join([c for c in nfkd if not unicodedata.combining(c)]).replace('đ', 'd').replace('Đ', 'D').lower()
        words = re.findall(r'[a-zA-Z0-9]+', ascii_t)
        variants = []
        if words:
            variants.append(''.join(words))
            if len(words) >= 3:
                variants.append(words[0] + words[1] + words[-1])
                variants.append(''.join(words[:-1]))
                variants.append(words[0] + words[-1])
        return list(dict.fromkeys(variants))

    def check_candidate_worker(c):
        raw_c = c.replace('http://', '').replace('https://', '').split('/')[0].strip()
        try:
            to_try = [c]
            if not c.startswith("http"):
                to_try = [f"https://{c}", f"http://{c}"]
            for t in to_try:
                try:
                    req = urllib.request.Request(t, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    with fetch_url(req, timeout=4.0) as resp:
                        final_u = resp.geturl() or t
                        html = resp.read(524288).decode("utf-8", errors="ignore")
                        is_btn = any(w in html for w in [
                            'trade-btn', 'trade-btn-clf', 'traffic-button', 'pages.dev/traffic', 'pages.dev/bt',
                            'pages.dev', 'mammon', 'pages.dev/andanh', 'ontops.link', 'client.gtraffic.io',
                            'dr-client.gtraffic.io', 'captchano', 'verifyclf', 'btf.js', 'btd.js', 'bt.js', 'lấy mã', 'lay ma'
                        ])
                        if is_btn:
                            return (final_u, final_u)
                except urllib.error.HTTPError:
                    pass
                except Exception:
                    pass
        except Exception:
            pass
        return (None, None)

    kw_clean = (keyword_text or "").lower().strip()

    # 1. Match known campaigns / rule triggers FIRST IF VERIFIED LIVE
    if kw_clean:
        for triggers, d_list in CAMPAIGN_RULES:
            if isinstance(d_list, str):
                d_list = [d_list]
            if any(t in kw_clean for t in triggers):
                for dom in d_list:
                    verified, _ = check_candidate_worker(dom)
                    if verified:
                        log(f"[+] Match known campaign triggers {triggers} and verified live: {verified}")
                        return verified

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 2. Check campaign image OCR FIRST
    if img_url:
        norm_img = img_url.strip()
        is_local = os.path.exists(norm_img)
        if is_local:
            temp_img = norm_img
        else:
            if norm_img.startswith("data:image"):
                pass
            elif norm_img.startswith("//"):
                norm_img = "https:" + norm_img
            elif norm_img.startswith("/"):
                norm_img = "https://gtraffic.io" + norm_img
            elif not norm_img.startswith("http"):
                norm_img = "https://cdn.gtraffic.io/" + norm_img.lstrip("/")

            temp_img = os.path.join(ROOT_DIR, "data", "temp", "gtraffic_camp.png")
            os.makedirs(os.path.dirname(temp_img), exist_ok=True)
        try:
            if is_local:
                pass
            elif norm_img.startswith("data:image"):
                import base64
                b64_data = norm_img.split(",", 1)[1] if "," in norm_img else norm_img
                with open(temp_img, "wb") as f:
                    f.write(base64.b64decode(b64_data))
            else:
                log(f"[*] Downloading campaign image for OCR: {norm_img}")
                req = urllib.request.Request(norm_img, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://gtraffic.io/"
                })
                with fetch_url(req, timeout=8) as resp, open(temp_img, "wb") as f:
                    f.write(resp.read())
            ocr = get_ocr()
            res, _ = ocr(temp_img)
            lines = [line[1] for line in (res or [])]
            log(f"[*] OCR extracted {len(lines)} lines from campaign image: {lines[:3]}")
            candidates = extract_domain_candidates(lines)

            # 2a. Match known campaigns against image OCR lines FIRST
            ocr_full_str = ' '.join(lines).lower()
            for triggers, d_list in CAMPAIGN_RULES:
                if isinstance(d_list, str):
                    d_list = [d_list]
                if any(t in ocr_full_str for t in triggers):
                    for dom in d_list:
                        verified, _ = check_candidate_worker(dom)
                        if verified:
                            log(f"[+] Match known campaign triggers in OCR {triggers} and verified live: {verified}")
                            return verified

            # 2b. Filter candidates & expand subdomains / variants / masked stems
            filtered_candidates = []
            kw_words = re.findall(r'[a-zA-Z0-9]+', kw_clean)
            for c in (candidates or []):
                h = c.split('.')[0].replace('www.', '')
                if len(h) >= 3:
                    filtered_candidates.append(c)
                    if len(candidates) < 15:
                        for ext_tld in ['com.co', 'com.vn', 'co', 'vn', 'in', 'net', 'org']:
                            filtered_candidates.append(f"{h}.{ext_tld}")
                    if kw_words and not c.startswith(kw_words[0]):
                        filtered_candidates.append(f"{kw_words[0]}.{c}")
                        for ext_tld in ['in', 'com.co', 'com.vn', 'org', 'net']:
                            filtered_candidates.append(f"{kw_words[0]}.{h}.{ext_tld}")

            # Expand masked stems for likely domain words
            stem_expansions = ['lana', 'lan', 'lunya', 'farming', 'walk', 'market', 'news', 'bet', 'vip', 'top', 'club', 'app', 'link', 'game', 'play', 'live', 'online', 'asia']
            for line_txt in lines:
                if any(ext in line_txt.lower() for ext in ['.com', '.net', '.in', '.co', '.vn', 'https:', 'http:']):
                    for w in re.findall(r'[a-zA-Z0-9]{4,}', line_txt):
                        wl = w.lower()
                        if wl in ['http', 'https', 'cung', 'nhat', '2025', '2026', 'chinh', 'dung']: continue
                        for ext_tld in ['net', 'com', 'com.co', 'com.vn', 'in.net', 'in', 'co']:
                            filtered_candidates.append(f"{wl}.{ext_tld}")
                            for exp in stem_expansions:
                                filtered_candidates.append(f"{wl}{exp}.{ext_tld}")
                                for cut in range(1, min(3, len(wl))):
                                    filtered_candidates.append(f"{wl[:-cut]}{exp}.{ext_tld}")

            filtered_candidates = list(dict.fromkeys(filtered_candidates))[:300]

            if filtered_candidates:
                log(f"[*] Fast parallel probing {len(filtered_candidates)} candidates from image: {filtered_candidates[:5]}...")
                with ThreadPoolExecutor(max_workers=min(30, len(filtered_candidates))) as ex:
                    futures = {ex.submit(check_candidate_worker, c): c for c in filtered_candidates}
                    for fut in as_completed(futures):
                        verified, _ = fut.result()
                        if verified:
                            log(f"[+] Found verified live sponsor from image: {verified}")
                            return verified
        except Exception as e:
            log(f"[!] OCR resolution note: {e}")
        finally:
            if os.path.exists(temp_img):
                try: os.remove(temp_img)
                except Exception: pass

    # 3. Check slug candidates as last resort
    slugs = generate_slug_variants(kw_clean)
    slug_candidates = []
    for slug in slugs:
        if len(slug) >= 3 and not slug.isdigit():
            for tld in ['com', 'vn', 'net', 'org', 'com.vn', 'info']:
                slug_candidates.append(f"{slug}.{tld}")

    if slug_candidates:
        with ThreadPoolExecutor(max_workers=min(20, len(slug_candidates))) as ex:
            futures = [ex.submit(check_candidate_worker, c) for c in slug_candidates[:25]]
            for fut in as_completed(futures):
                verified, _ = fut.result()
                if verified:
                    log(f"[+] Found verified live sponsor from slug: {verified}")
                    return verified
    return None

def run(target_url: str = None, headless: bool = True):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "https://gtraffic.io/X3BR2OQ"

    if "--head" in sys.argv or "-w" in sys.argv or "--window" in sys.argv:
        headless = False
    elif "--headless" in sys.argv or "-h" in sys.argv or os.environ.get("GTRAFFIC_HEADLESS") == "1":
        headless = True

    log(f"[*] Target Gtraffic URL: {target_url}")
    log(f"[*] Starting Gtraffic Autonomous Engine (Headless: {headless})...")

    proxies = load_proxies()
    proxy_cfg = None
    proxy_opener = None
    if proxies:
        p0 = proxies[0]
        proxy_cfg = {
            "server": p0["server"],
            "username": p0.get("username", ""),
            "password": p0.get("password", "")
        }
        p_auth = f"{p0['username']}:{p0['password']}@" if p0.get("username") else ""
        p_url = p0["server"].replace("http://", f"http://{p_auth}")
        proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": p_url, "https": p_url}))
        log(f"[+] Active Residential Proxy: {p0['server']}")

    def call_api(req, timeout=8):
        if proxy_opener:
            return proxy_opener.open(req, timeout=timeout)
        return urllib.request.urlopen(req, timeout=timeout)

    initial_sponsor = None
    g_data = {}
    session_rid = str(uuid.uuid4())
    try:
        is_direct = "direct.gtraffic.io" in target_url or "dr-client" in target_url
        slug = target_url.split("?")[0].split("#")[0].strip().rstrip("/").split("/")[-1]
        session_rid = str(uuid.uuid4())
        probe_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": target_url,
            "Content-Type": "application/json",
            "rid": session_rid
        }
        if is_direct:
            api_url = f"https://dr-client.gtraffic.io/api/url/get?id={slug}&deviceType=desktop"
        else:
            api_url = f"https://client.gtraffic.io/api/url/get?id={slug}&deviceType=desktop"

        d_req = urllib.request.Request(api_url, headers=probe_headers)
        with call_api(d_req, timeout=6) as d_res:
            g_data = json.loads(d_res.read().decode("utf-8", errors="ignore"))

        if g_data:
            dl = g_data.get("data_link")
            if isinstance(dl, dict) and dl.get("url") and is_valid_destination(dl.get("url"), initial_sponsor):
                final_leak = dl.get("url")
                log(f"🎉 FAST ZERO-WAIT DIRECT LEAK DETECTED: {final_leak}")
                try:
                    with open(DEST_FILE, "w", encoding="utf-8") as f:
                        f.write(str(final_leak))
                    with open(os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), "w", encoding="utf-8") as f:
                        f.write(str(final_leak))
                except Exception:
                    pass
                copy_to_clipboard(str(final_leak))
                return
            if g_data.get("url_dr"):
                initial_sponsor = g_data.get("url_dr")
                log(f"[+] Direct GTraffic Sponsor pre-resolved via API url_dr: {initial_sponsor}")
            elif g_data.get("data_keyword"):
                dk_pre = g_data["data_keyword"]
                kw_t = dk_pre.get("keyword_text")
                kw_img = dk_pre.get("keyword_image")
                if not kw_t and kw_img:
                    try:
                        import base64
                        b64 = kw_img.split(",", 1)[1] if "," in kw_img else kw_img
                        ocr = get_ocr()
                        res_kw, _ = ocr(base64.b64decode(b64))
                        kw_t = " ".join([l[1] for l in (res_kw or [])]).strip()
                    except Exception:
                        pass
                src_t = dk_pre.get("source") or dk_pre.get("source_2")
                if kw_t or src_t:
                    initial_sponsor = resolve_sponsor_domain(kw_t or "", src_t, opener=proxy_opener)
                    if initial_sponsor:
                        log(f"[+] GTraffic Sponsor pre-resolved via API: {initial_sponsor}")
    except Exception as e:
        log(f"[*] Pre-probe note: {e}")

    ext_dir = os.path.abspath(os.path.join(ROOT_DIR, "src", "extensions", "turnstile_patch"))
    user_data_dir = os.path.join(ROOT_DIR, "data", "temp", "chrome_gtraffic_profile")
    if os.path.exists(user_data_dir):
        shutil.rmtree(user_data_dir, ignore_errors=True)

    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--no-first-run",
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding"
    ]
    if os.path.exists(ext_dir):
        args.extend([
            f"--disable-extensions-except={ext_dir}",
            f"--load-extension={ext_dir}"
        ])

    with sync_playwright() as p:
        if IS_PATCHRIGHT:
            browser = p.chromium.launch(
                headless=headless,
                proxy=proxy_cfg
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 850},
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                ignore_https_errors=True
            )
        else:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=CHROME_PATH,
                headless=headless,
                args=args,
                proxy=proxy_cfg,
                viewport={"width": 1280, "height": 850},
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                ignore_https_errors=True
            )
            browser = context

        final_destination = None

        # TAB 1: Gtraffic Page
        page1 = context.pages[0] if context.pages else context.new_page()
        campaign_info = {}
        sponsor_domain = initial_sponsor

        def on_gtraffic_request(req):
            nonlocal session_rid
            h = req.headers
            if "rid" in h and h["rid"]:
                session_rid = h["rid"]

        page1.on("request", on_gtraffic_request)

        def on_gtraffic_response(res):
            nonlocal final_destination
            u = res.url
            # Capture campaign info & Direct Link Leak
            if "api/url/get" in u or ("api/url" in u and "tracking" not in u and "done" not in u):
                try:
                    data = res.json()
                    # Check for Direct URL Leak (Campaign empty / budget exhausted)
                    dl = data.get("data_link")
                    if isinstance(dl, dict) and dl.get("url") and is_valid_destination(dl.get("url"), sponsor_domain):
                        final_destination = dl.get("url")
                        log(f"🎉 DIRECT URL LEAK DETECTED IN api/url/get: {final_destination}")
                    elif isinstance(dl, str) and is_valid_destination(dl, sponsor_domain):
                        final_destination = dl
                        log(f"🎉 DIRECT URL LEAK DETECTED IN api/url/get: {final_destination}")

                    dk = data.get("data_keyword") or {}
                    if dk:
                        campaign_info["data_keyword"] = dk
                    kw_t = dk.get("keyword_text")
                    kw_img = dk.get("keyword_image")
                    src_t = dk.get("source") or dk.get("source_2")
                    if kw_t is not None:
                        campaign_info["keyword_text"] = kw_t
                    elif kw_img:
                        try:
                            import base64
                            b64 = kw_img.split(",", 1)[1] if "," in kw_img else kw_img
                            ocr = get_ocr()
                            res_kw, _ = ocr(base64.b64decode(b64))
                            kw_ocr = " ".join([l[1] for l in (res_kw or [])]).strip()
                            if kw_ocr:
                                campaign_info["keyword_text"] = kw_ocr
                                log(f"[TAB 1] OCR Extracted keyword from API keyword_image: '{kw_ocr}'")
                        except Exception:
                            pass
                    if src_t is not None:
                        campaign_info["source"] = src_t
                    
                    dr_url = data.get("url_dr")
                    if dr_url and isinstance(dr_url, str) and dr_url.startswith("http"):
                        campaign_info["url_dr"] = dr_url
                        sponsor_domain = dr_url
                        log(f"[TAB 1] 💎 Direct Gtraffic Sponsor URL in API: {sponsor_domain}")
                    elif kw_t and not sponsor_domain:
                        # Direct GTraffic might return domain in keyword_text (e.g. designkids.info)
                        direct_cand = resolve_sponsor_domain(kw_t, src_t, opener=proxy_opener)
                        if direct_cand:
                            sponsor_domain = direct_cand
                            campaign_info["url_dr"] = direct_cand
                            log(f"[TAB 1] 💎 Direct Gtraffic Sponsor resolved from keyword_text: {sponsor_domain}")

                    log(f"[TAB 1] Active Campaign: '{campaign_info.get('keyword_text')}' | Image: {campaign_info.get('source')} | DR: {campaign_info.get('url_dr')}")
                except Exception:
                    pass
            # Capture final tracking URL or any response containing destinations
            if "gtraffic.io" in u:
                try:
                    ct = res.headers.get("content-type", "")
                    if "json" in ct:
                        data = res.json()
                        dl = data.get("data_link")
                        if isinstance(dl, dict) and dl.get("url") and is_valid_destination(dl.get("url"), sponsor_domain):
                            final_destination = dl.get("url")
                            log(f"🎉 DESTINATION URL INTERCEPTED FROM DATA_LINK: {final_destination}")
                        elif isinstance(dl, str) and is_valid_destination(dl, sponsor_domain):
                            final_destination = dl
                            log(f"🎉 DESTINATION URL INTERCEPTED FROM DATA_LINK STR: {final_destination}")
                        for k in ["result", "url", "link", "destination", "redirect", "redirect_url"]:
                            val = data.get(k)
                            if isinstance(val, str) and is_valid_destination(val, sponsor_domain):
                                final_destination = val
                                log(f"🎉 DESTINATION URL INTERCEPTED FROM API: {final_destination}")
                                break
                except Exception:
                    pass

        def on_page1_nav(frame):
            nonlocal final_destination
            if frame == page1.main_frame:
                u = frame.url
                if is_valid_destination(u, sponsor_domain):
                    final_destination = u
                    log(f"🎉 DESTINATION URL INTERCEPTED FROM NAVIGATION: {final_destination}")

        page1.on("framenavigated", on_page1_nav)
        page1.on("response", on_gtraffic_response)

        log("[TAB 1] Navigating to Gtraffic shortlink...")
        try:
            page1.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            log(f"[!] Warning on initial goto: {e}")
        
        # Check if direct link was already leaked
        time.sleep(1)
        if final_destination and is_valid_destination(final_destination):
            log(f"🎉 Bypassed via Direct URL Leak without opening sponsor tab: {final_destination}")
            try:
                with open(DEST_FILE, "w", encoding="utf-8") as f:
                    f.write(str(final_destination))
                with open(os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), "w", encoding="utf-8") as f:
                    f.write(str(final_destination))
            except Exception:
                pass
            copy_to_clipboard(str(final_destination))
            browser.close()
            return
        
        # Ensure page1 passes Cloudflare Turnstile and renders form before opening Tab 2
        log("[TAB 1] Waiting for Gtraffic page to load (passing Cloudflare if needed)...")
        for _ in range(25):
            time.sleep(1)
            t_low = page1.title().lower()
            inp_ready = page1.locator('input[placeholder*="Nhập mã"], input[type="text"]:not([readonly])').first
            if (inp_ready.count() > 0 and inp_ready.is_visible()) or ("gtraffic" in t_low and "web" in t_low):
                log("[TAB 1] ✔ Gtraffic page and form are ready!")
                break
            try:
                for f in page1.frames:
                    if "challenges.cloudflare.com" in f.url:
                        cb = f.locator("input[type='checkbox'], label, #challenge-stage, .mark, body").first
                        if cb.count() > 0: cb.click(timeout=1000)
                ifr = page1.locator("iframe[src*='challenges.cloudflare.com']").first
                if ifr.count() > 0:
                    box = ifr.bounding_box()
                    if box: page1.mouse.click(box["x"] + 35, box["y"] + box["height"] / 2)
            except Exception:
                pass

        for attempt in range(1, 4):
            if is_valid_destination(final_destination, sponsor_domain):
                break
            log(f"\n--- [GTRAFFIC CAMPAIGN ATTEMPT {attempt}/3] ---")
            if attempt > 1:
                log("[TAB 1] Refreshing mission via 'Đổi từ khóa mới'...")
                try:
                    btn_change = page1.locator('button:has-text("Đổi từ khóa mới"), button:has-text("Đổi từ khóa"), button:has-text("đổi từ khóa")').first
                    if btn_change.count() > 0:
                        btn_change.scroll_into_view_if_needed()
                        btn_change.click()
                        time.sleep(3)
                    campaign_info.clear()
                    sponsor_domain = None
                except Exception as e_change:
                    log(f"[!] Note on mission change: {e_change}")

            if not campaign_info.get("url_dr") and not sponsor_domain:
                for _ in range(20):
                    try:
                        dom_camp = page1.evaluate("""() => {
                            let img = '';
                            let kw = '';
                            let kw_b64 = '';
                            const imgEl = document.querySelector('img.gallery-item, img[alt*="tim kiem"], img[src*="cdn.gtraffic.io"], .instruction img, #instruction img');
                            if (imgEl && imgEl.src && !imgEl.src.endsWith('.svg')) img = imgEl.src;

                            const kwEl = document.querySelector('.google-text-font, #keyword, .keyword-text, [data-keyword], input[readonly], .copy-text');
                            if (kwEl) {
                                const val = (kwEl.innerText || kwEl.value || kwEl.textContent || '').trim();
                                if (val && !val.includes('ĐIỀU HƯỚNG') && !val.includes('HỆ THỐNG')) kw = val;
                            }

                            const kwImg = document.querySelector('img[alt*="Từ khóa"], img[alt*="nhiệm vụ"], foreignObject img');
                            if (kwImg && kwImg.src) kw_b64 = kwImg.src;

                            return { img, kw, kw_b64 };
                        }""")
                        if dom_camp.get("img") and not campaign_info.get("source"):
                            campaign_info["source"] = dom_camp["img"]
                        if dom_camp.get("kw") and not campaign_info.get("keyword_text"):
                            campaign_info["keyword_text"] = dom_camp["kw"].strip()
                        if dom_camp.get("kw_b64") and not campaign_info.get("keyword_text"):
                            try:
                                import base64
                                b64 = dom_camp["kw_b64"].split(",", 1)[1] if "," in dom_camp["kw_b64"] else dom_camp["kw_b64"]
                                kw_bytes = base64.b64decode(b64)
                                ocr = get_ocr()
                                res_kw, _ = ocr(kw_bytes)
                                kw_ocr_str = " ".join([l[1] for l in (res_kw or [])]).strip()
                                if kw_ocr_str:
                                    campaign_info["keyword_text"] = kw_ocr_str
                                    log(f"[TAB 1] OCR Extracted keyword from task image: '{kw_ocr_str}'")
                            except Exception:
                                pass
                        if campaign_info.get("source") and campaign_info.get("keyword_text"):
                            break
                    except Exception:
                        pass
                    time.sleep(0.2)

            # Resolve sponsor domain
            if not sponsor_domain:
                if campaign_info.get("url_dr"):
                    sponsor_domain = campaign_info.get("url_dr")
                    log(f"[+] Using Direct Gtraffic sponsor URL: {sponsor_domain}")
                else:
                    kw = campaign_info.get("keyword_text", "")
                    img = campaign_info.get("source", "")
                    log(f"[TAB 1] Active Campaign: '{kw}' | Image: {img}")
                    sponsor_domain = resolve_sponsor_domain(kw, img, opener=proxy_opener)

            # Element Screenshot OCR fallback if sponsor_domain is still None
            if not sponsor_domain:
                try:
                    img_loc = page1.locator('img.gallery-item, img[alt*="tim kiem"], img[src*="cdn.gtraffic.io"], .instruction img').first
                    if img_loc.count() > 0:
                        temp_canvas = os.path.join(ROOT_DIR, "data", "temp", "canvas_gtraffic.png")
                        os.makedirs(os.path.dirname(temp_canvas), exist_ok=True)
                        img_loc.screenshot(path=temp_canvas)
                        ocr = get_ocr()
                        res_c, _ = ocr(temp_canvas)
                        lines_c = [l[1] for l in (res_c or [])]
                        log(f"[TAB 1] Instruction element OCR extracted: {lines_c}")
                        sponsor_domain = resolve_sponsor_domain(kw, temp_canvas, opener=proxy_opener)
                        if sponsor_domain:
                            log(f"[+] Recovered sponsor domain via element OCR: {sponsor_domain}")
                        if os.path.exists(temp_canvas):
                            try: os.remove(temp_canvas)
                            except Exception: pass
                except Exception as e_canvas:
                    log(f"[*] Element OCR note: {e_canvas}")

            if not sponsor_domain:
                log(f"[!] Could not determine sponsor website on attempt {attempt}.")
                continue

            log(f"🎉 TARGET SPONSOR WEBSITE FOR GTRAFFIC: {sponsor_domain}")

            # TAB 2: Sponsor Website
            page2 = context.new_page()
            page2.set_viewport_size({"width": 1280, "height": 800})

            # Load real andanh.js with math helpers
            andanh_file = os.path.join(ROOT_DIR, "src", "core", "andanh.js")
            real_andanh_code = ""
            if os.path.exists(andanh_file):
                try:
                    with open(andanh_file, "r", encoding="utf-8") as f_an:
                        real_andanh_code = f_an.read()
                except Exception:
                    pass

            if real_andanh_code:
                page2.route("**/andanh.js", lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=real_andanh_code
                ))

            # 1. Neutralize detectIncognito cleanly & inject stealth in page2
            page2.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(window, 'detectIncognito', {
                    get: () => () => Promise.resolve({ isPrivate: false, browserName: 'Chrome' }),
                    set: () => {},
                    configurable: false
                });
                window.alert = function() {};
                try {
                    Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
                    Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
                    window.hasFocus = () => true;
                } catch (e) {}
                if (window.navigator && window.navigator.webkitTemporaryStorage) {
                    window.navigator.webkitTemporaryStorage.queryUsageAndQuota = function(s, e) {
                        if (typeof s === 'function') s(100, 100000000000);
                    };
                }
            """)

            extracted_code = None

            def on_page2_response(res):
                nonlocal extracted_code
                if extracted_code:
                    return
                try:
                    if any(k in res.url for k in ["api/code", "process-code"]):
                        data = res.json()
                        c = data.get("code") or data.get("data") or data.get("token") or data.get("c")
                        if isinstance(c, dict):
                            c = c.get("code") or c.get("token")
                        if c and isinstance(c, str):
                            c_str = c.strip()
                            if 4 <= len(c_str) <= 25 and not any(w in c_str.lower() for w in ["wait", "giây", "chờ", "vui"]):
                                extracted_code = c_str
                                log(f"\n==========================================")
                                log(f"💎 EXTRACTED CODE FROM NETWORK API: {extracted_code}")
                                log(f"==========================================\n")
                except Exception:
                    pass

            page2.on("response", on_page2_response)

            is_direct = "direct.gtraffic.io" in target_url or "dr-client" in target_url
            ref_header = "" if is_direct else "https://www.google.com/"
            log(f"[TAB 2] Opening sponsor site (Direct={is_direct}): {sponsor_domain}")
            try:
                if ref_header:
                    page2.goto(sponsor_domain, wait_until="domcontentloaded", referer=ref_header, timeout=40000)
                else:
                    page2.goto(sponsor_domain, wait_until="domcontentloaded", timeout=40000)
            except Exception as e:
                log(f"[!] Warning on sponsor goto: {e}")
            time.sleep(2)

            # Clear runb, flag1, runr, cmnmf, mtkf, doneg, coo3, coo4, can cookies so click triggers freshly
            try:
                page2.evaluate("""() => {
                    const cookies = ['runb', 'flag1', 'runr', 'cmnmf', 'mtkf', 'doneg', 'coo3', 'coo4', 'can'];
                    cookies.forEach(c => {
                        document.cookie = c + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
                        document.cookie = c + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=' + window.location.hostname + ';';
                    });
                    document.querySelectorAll('body > *').forEach(el => {
                        el.style.visibility = 'visible';
                        el.style.opacity = '1';
                    });
                    document.querySelectorAll('.modal, .popup, #ad_banner').forEach(el => el.remove());
                }""")
            except Exception:
                pass

            # Locate GTraffic button (handles trade-btn-clf, traffic-button-no, trade-btn, trade-d-btn, etc.)
            btn_selector = '#trade-btn-clf svg, #trade-btn-clf, #trade-btn, #trade-d-btn, .trade-d-btn-container, #traffic-button-no, .trade-btn-clf, .trade-btn, #trade-d-btn button, #trade-d-btn a, button:has-text("LẤY MÃ"), a:has-text("LẤY MÃ"), [id*="trade-btn"]'
            log(f"[TAB 2] Scrolling to locate Gtraffic button...")

            # Scroll to bottom first
            try:
                page2.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            except Exception:
                pass

            btn = None
            for _ in range(15):
                candidates = page2.locator(btn_selector)
                for idx in range(candidates.count()):
                    c_el = candidates.nth(idx)
                    box = c_el.bounding_box()
                    if box and (box['height'] > 5 or box['width'] > 5):
                        btn = c_el
                        break
                if btn:
                    break
                page2.mouse.wheel(0, 500)
                time.sleep(0.3)

            if not btn:
                log("[TAB 2] Button not found on sponsor landing page, scanning for articles...")
                try:
                    art_cands = page2.evaluate("""(sp_url) => {
                        const host = new URL(sp_url).hostname.replace(/^www\\./, '').toLowerCase();
                        const links = [];
                        document.querySelectorAll('article a[href], .post a[href], h1 a[href], h2 a[href], h3 a[href], main a[href], a[href]').forEach(a => {
                            try {
                                const u = new URL(a.href, window.location.href);
                                const uHost = u.hostname.replace(/^www\\./, '').toLowerCase();
                                if (uHost === host && u.pathname.length > 3 && !u.pathname.includes('wp-admin') && !u.href.includes('#')) {
                                    links.push(u.href.replace(/\\/$/, ''));
                                }
                            } catch (e) {}
                        });
                        return Array.from(new Set(links));
                    }""", sponsor_domain)
                    if art_cands:
                        log(f"[TAB 2] Navigating to article on sponsor site: {art_cands[0]}")
                        try:
                            page2.goto(art_cands[0], wait_until="domcontentloaded", timeout=30000)
                            time.sleep(1.5)
                            try:
                                page2.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                time.sleep(1)
                            except Exception:
                                pass
                            for _ in range(15):
                                candidates = page2.locator(btn_selector)
                                for idx in range(candidates.count()):
                                    c_el = candidates.nth(idx)
                                    box = c_el.bounding_box()
                                    if box and (box['height'] > 5 or box['width'] > 5):
                                        btn = c_el
                                        break
                                if btn:
                                    break
                                page2.mouse.wheel(0, 500)
                                time.sleep(0.3)
                        except Exception:
                            pass
                except Exception:
                    pass

            # Trigger click with JavaScript for all button variants
            try:
                page2.evaluate("""() => {
                    const targets = [
                        document.querySelector('#trade-btn-clf svg'),
                        document.getElementById('trade-btn-clf'),
                        document.getElementById('trade-d-btn'),
                        document.querySelector('.trade-d-btn-container'),
                        document.getElementById('trade-btn'),
                        document.getElementById('traffic-button-no')
                    ].filter(Boolean);
                    for (const el of targets) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        if (typeof el.onclick === 'function') el.onclick();
                        el.click();
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    }
                }""")
            except Exception:
                pass

            if btn:
                try:
                    btn.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    btn.click(force=True, timeout=3000)
                except Exception:
                    pass

            log("⚡ KÍCH HOẠT: Đã nhấn nút 'LẤY MÃ' ➔ Bộ đếm bắt đầu chạy!")

            # Check for CaptchaNo challenge
            time.sleep(1.5)
            is_captcha = page2.evaluate("""() => {
                const c = document.querySelector('.captchano-container');
                return c && !c.classList.contains('hidden');
            }""")

            if is_captcha:
                log("[!] CaptchaNo challenge detected! Solving...")
                for _ in range(10):
                    src = page2.evaluate("() => document.getElementById('captchano-img')?.src || ''")
                    if src and len(src) > 50:
                        break
                    time.sleep(0.5)

                opts = page2.evaluate("() => Array.from(document.querySelectorAll('input[name=\"captchano-choice\"]')).map(el => el.value)")
                chosen_opt = None
                if src.startswith("data:image"):
                    import base64
                    b64 = src.split(",", 1)[1]
                    img_bytes = base64.b64decode(b64)
                    ocr = get_ocr()
                    res, _ = ocr(img_bytes)
                    ocr_text = " ".join([line[1] for line in (res or [])])
                    for opt in opts:
                        if opt in ocr_text:
                            chosen_opt = opt
                            break

                if not chosen_opt and opts:
                    chosen_opt = opts[0]

                if chosen_opt:
                    page2.evaluate(f"""() => {{
                        const r = document.querySelector('input[name="captchano-choice"][value="{chosen_opt}"]');
                        if (r) {{
                            r.checked = true;
                            r.dispatchEvent(new Event('change'));
                        }}
                        const s = document.getElementById('captchano-submit');
                        if (s) s.click();
                    }}""")
                    time.sleep(1.5)

            # Countdown wait loop with continuous anti-stall scrolling (~95s max)
            for s in range(1, 95):
                if extracted_code:
                    break

                # Anti-stall scrolling satisfies is_scroll2 requirement
                page2.mouse.wheel(0, 100 if (s % 2 == 0) else -100)
                time.sleep(1)

                dom_data = page2.evaluate("""() => {
                    const c = document.querySelector('#trade-btn-clf__content, #trade-btn__content, #traffic-button-no__content, [id$="__content"]');
                    const b = document.querySelector('#trade-btn-clf, #trade-btn, #traffic-button-no, #trade-d-btn, #notice-btn, [id*="trade-btn"]');
                    const btnCodes = Array.from(document.querySelectorAll('[id*="trade-btn"][data-code], [id*="traffic-button"][data-code], .trade-btn[data-code]')).map(el => el.dataset.code);
                    return {
                        content: (c && c.textContent) || "",
                        btn: (b && b.textContent) || "",
                        btnCodes: btnCodes
                    };
                }""")

                c_val = str(dom_data.get("content", "")).strip()
                if s % 10 == 0 or (s >= 55 and s % 2 == 0) or (c_val and not c_val.isdigit()):
                    if s % 10 == 0 or s >= 55:
                        log(f"  [Countdown] {s}s elapsed | Content: '{c_val}'")

                # Check if content has transformed into code after countdown
                if c_val and not c_val.isdigit() and len(c_val) >= 4 and (s >= 50 or c_val == '0'):
                    cleaned = re.sub(r'^(?:Code|M[ãa]|M[ãa]\s*x[áa]c\s*nh[ậa]n|M[ãa]\s*KM)[\s\:\-]+', '', c_val, flags=re.IGNORECASE).strip()
                    if cleaned and not any(w in cleaned.lower() for w in ["giây", "chờ", "vui lòng", "robot", "lấy mã"]):
                        extracted_code = cleaned
                        log(f"\n==========================================")
                        log(f"💎 EXTRACTED GTRAFFIC CODE FROM CONTENT: {extracted_code}")
                        log(f"==========================================\n")
                        break

                # Check data-code strictly after countdown
                if s >= 50 or c_val == '0':
                    for val in dom_data.get("btnCodes", []):
                        v_clean = str(val).strip()
                        if re.match(r'^[A-Za-z0-9]{5,20}$', v_clean) and not any(w in v_clean.lower() for w in ["giay", "giây", "code", "wait", "button"]):
                            extracted_code = v_clean
                            log(f"\n==========================================")
                            log(f"💎 EXTRACTED CODE FROM BUTTON DATA-CODE: {extracted_code}")
                            log(f"==========================================\n")
                            break

            if not extracted_code:
                # Strictly check if trade-btn has final data-code attribute
                try:
                    final_code = page2.evaluate("() => document.getElementById('trade-btn-clf')?.getAttribute('data-code') || document.getElementById('trade-btn')?.getAttribute('data-code') || document.getElementById('trade-btn-clf__content')?.textContent || ''").strip()
                    if final_code and not final_code.isdigit() and len(final_code) >= 5 and not any(w in final_code.lower() for w in ["f5", "lại", "trang", "code", "wait", "giây"]):
                        extracted_code = final_code
                        log(f"💎 EXTRACTED CODE FROM FINAL ELEMENT: {extracted_code}")
                except Exception:
                    pass

            try: page2.close()
            except Exception: pass

            if not extracted_code:
                log(f"[!] Could not retrieve verification code on attempt {attempt}.")
                continue

            # Write code to extracted_code.txt
            try:
                with open(CODE_FILE, "w", encoding="utf-8") as fc:
                    fc.write(extracted_code)
            except Exception:
                pass

            # Switch back to TAB 1 to submit code
            log("[TAB 1] Switching back to Gtraffic tab to submit code...")
            page1.bring_to_front()
            time.sleep(0.5)
            t_cur = page1.title().lower()
            log(f"[TAB 1] Current Page State -> URL: {page1.url} | Title: {page1.title()}")
            if "gtraffic" not in t_cur:
                log("[TAB 1] Fresh navigation to Gtraffic to submit code...")
                try:
                    page1.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass

            # Wait up to 25s for input to be visible (handle Turnstile if present)
            inp = None
            last_ts_click = 0
            for loop_idx in range(50):
                inp_cand = page1.locator('input[placeholder*="Nhập mã"], input[placeholder*="xác nhận"], input[type="text"]:not([readonly])').first
                if inp_cand.count() > 0 and inp_cand.is_visible():
                    inp = inp_cand
                    log("[TAB 1] ✔ Code input form is ready!")
                    break
                now = time.time()
                if now - last_ts_click > 3.5:
                    try:
                        clicked = False
                        for f in page1.frames:
                            if "challenges.cloudflare.com" in f.url:
                                chk = f.locator("input[type='checkbox'], label, #challenge-stage, .mark, body").first
                                if chk.count() > 0:
                                    chk.click(timeout=1000)
                                    log("[TAB 1] Clicked Turnstile checkbox in challenge frame")
                                    last_ts_click = now
                                    clicked = True
                                    break
                        if not clicked:
                            ifr = page1.locator('iframe[src*="challenges.cloudflare.com"]').first
                            if ifr.count() > 0:
                                box = ifr.bounding_box()
                                if box:
                                    page1.mouse.click(box['x'] + 35, box['y'] + box['height'] / 2)
                                    last_ts_click = now
                    except Exception:
                        pass
                time.sleep(0.5)

            if inp and inp.count() > 0:
                inp.scroll_into_view_if_needed()
                inp.click()
                inp.fill("")
                time.sleep(0.1)
                inp.fill(extracted_code)
                page1.keyboard.type(" ", delay=10)
                page1.keyboard.press("Backspace")
                inp.dispatch_event("input")
                inp.dispatch_event("change")
                log(f"[+] Filled code '{extracted_code}' into Gtraffic form!")

            time.sleep(0.5)
            # Listen to popups strictly from page1 after code submission
            def on_final_popup(p):
                def on_pop_nav(frame):
                    nonlocal final_destination
                    if frame == p.main_frame:
                        u = frame.url
                        if is_valid_destination(u, sponsor_domain):
                            final_destination = u
                            log(f"🎉 DESTINATION URL INTERCEPTED FROM POPUP: {final_destination}")
                p.on("framenavigated", on_pop_nav)
                if is_valid_destination(p.url, sponsor_domain):
                    final_destination = p.url
                    log(f"🎉 DESTINATION URL INTERCEPTED FROM POPUP URL: {final_destination}")

            context.on("page", on_final_popup)

            # Click submit button & press Enter
            submit_btn = page1.locator('button:has-text("Nhập mã xác nhận"), button:has-text("NHẬP MÃ XÁC NHẬN"), button:has-text("Nhập mã"), button:has-text("XÁC NHẬN")').first
            if submit_btn.count() > 0:
                submit_btn.scroll_into_view_if_needed()
                submit_btn.click()
                log("[+] Clicked 'Nhập mã xác nhận'!")
            try:
                page1.keyboard.press("Enter")
            except Exception:
                pass

            # Wait for destination URL (listen to network response, DOM link reveal, or navigation)
            log("[*] Waiting for destination URL unlock (up to 15s)...")
            for sec in range(15):
                time.sleep(1)
                if is_valid_destination(final_destination, sponsor_domain):
                    break
                # Check DOM for revealed link <a>
                try:
                    revealed_links = page1.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(h => h && h.startsWith('http') && !h.includes('gtraffic.io') && !h.includes('facebook') && !h.includes('twitter') && !h.includes('instagram') && !h.includes('telegram') && !h.includes('linkedin'));
                    }""")
                    for lk in (revealed_links or []):
                        if is_valid_destination(lk, sponsor_domain):
                            final_destination = lk
                            log(f"🎉 DESTINATION URL FOUND IN DOM LINK: {final_destination}")
                            break
                except Exception:
                    pass
                if is_valid_destination(final_destination, sponsor_domain):
                    break
                curr_url = page1.url
                if is_valid_destination(curr_url, sponsor_domain):
                    final_destination = curr_url
                    break

            # Fallback: Direct API submission using captured session rid
            if not final_destination or not is_valid_destination(final_destination, sponsor_domain):
                try:
                    log("[*] Attempting Direct API verification fallback (api/url/tracking-url)...")
                    kw_obj = campaign_info.get("data_keyword") or (g_data.get("data_keyword") if "g_data" in locals() and g_data else {})
                    kw_id = kw_obj.get("id") if kw_obj else None
                    kw_token = kw_obj.get("o") if kw_obj else None
                    kw_name = kw_obj.get("keyword_text") if kw_obj else campaign_info.get("keyword_text", "")
                    used_rid = session_rid if "session_rid" in locals() and session_rid else str(uuid.uuid4())
                    
                    if kw_id and extracted_code:
                        tracking_url = "https://client.gtraffic.io/api/url/tracking-url"
                        payload = {
                            "browser_name": "Chrome",
                            "browser_version": "124.0.0.0",
                            "os_name": "Windows",
                            "os_version": "10.0",
                            "os_version_name": "10",
                            "keyword_answer": extracted_code,
                            "link_shorten_id": slug,
                            "keyword": kw_name,
                            "ip": "",
                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                            "device_name": "desktop",
                            "token": kw_token or "",
                            "keyword_id": kw_id
                        }
                        api_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                            "Content-Type": "application/json",
                            "rid": used_rid,
                            "ncl": "000000000",
                            "Origin": "https://gtraffic.io",
                            "Referer": target_url
                        }
                        req_track = urllib.request.Request(tracking_url, data=json.dumps(payload).encode(), headers=api_headers)
                        with call_api(req_track, timeout=8) as r_t:
                            res_t = json.loads(r_t.read().decode("utf-8", errors="ignore"))
                            log(f"[*] tracking-url response: {res_t}")
                            dl_u = res_t.get("data_link", {}).get("url") if isinstance(res_t.get("data_link"), dict) else None
                            if dl_u and is_valid_destination(dl_u, sponsor_domain):
                                final_destination = dl_u
                                log(f"🎉 DESTINATION URL INTERCEPTED VIA DIRECT TRACKING-URL: {final_destination}")
                except Exception as e_api_sub:
                    log(f"[!] Direct API fallback note: {e_api_sub}")

            if is_valid_destination(final_destination, sponsor_domain):
                break

        if is_valid_destination(final_destination, sponsor_domain):
            log(f"\n==========================================")
            log(f"🎉 FINAL DESTINATION URL: {final_destination}")
            log(f"==========================================\n")
            try:
                with open(DEST_FILE, "w", encoding="utf-8") as f:
                    f.write(str(final_destination))
                run_id = os.environ.get("BYPASS_RUN_ID")
                if run_id:
                    with open(os.path.join(ROOT_DIR, f"destination_url-{run_id}.txt"), "w", encoding="utf-8") as f_run:
                        f_run.write(str(final_destination))
                with open(os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), "w", encoding="utf-8") as f_d:
                    f_d.write(str(final_destination))
                desk = os.path.expanduser(r"~\Desktop\destination_url.txt")
                with open(desk, "w", encoding="utf-8") as fd:
                    fd.write(str(final_destination))
            except Exception:
                pass
            copy_to_clipboard(str(final_destination))
        else:
            log("[!] Warning: Could not unlock final destination URL from Gtraffic.")

        try:
            browser.close()
        except Exception:
            pass
        if os.path.exists(user_data_dir):
            shutil.rmtree(user_data_dir, ignore_errors=True)

if __name__ == "__main__":
    run()
