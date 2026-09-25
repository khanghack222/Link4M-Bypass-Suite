import re
import time
import urllib.request
import ssl
import base64
import requests
from rapidocr_onnxruntime import RapidOCR
from config import log
try:
    from brain import get_brain
except ImportError:
    from src.core.brain import get_brain

_OCR_INSTANCE = None
def get_ocr():
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        _OCR_INSTANCE = RapidOCR()
    return _OCR_INSTANCE

def _ocr_cloud_api(img_bytes: bytes) -> str:
    """Gửi ảnh lên Cloud OCR API với timeout ngắn để tăng tốc tối đa."""
    if not img_bytes or len(img_bytes) < 100:
        return ""
    try:
        b64_img = "data:image/png;base64," + base64.b64encode(img_bytes).decode('utf-8')
        payload = {
            'base64Image': b64_img,
            'isOverlayRequired': False,
            'apikey': 'helloworld',
            'language': 'eng',
            'OCREngine': '2'
        }
        r = requests.post('https://api.ocr.space/parse/image', data=payload, timeout=5)
        if r.status_code == 200:
            parsed = r.json().get("ParsedResults", [])
            if parsed:
                return parsed[0].get("ParsedText", "").strip()
    except Exception:
        pass
    return ""

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

MEDIA_EXTS = {'jpg', 'png', 'webp', 'jpeg', 'gif', 'html', 'js', 'css', 'svg', 'mp3', 'mp4', 'json'}

def unmask_domain_candidates(raw_text: str):
    """Auto unmask domains with asterisks like shin-shih.co***.tw or site.c***"""
    results = []
    clean = raw_text.replace('★', '*').replace('x', 'x')

    # Pattern 1: domain.c***.tw / domain.co***.vn / domain.co***.tw
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.(?:co|c)\*+\.([a-zA-Z]{2,4})', clean, re.IGNORECASE):
        p, cc = m.group(1).lower(), m.group(2).lower()
        results.extend([f"{p}.com.{cc}", f"{p}.co.{cc}", f"{p}.{cc}"])

    # Pattern 2: domain.c*** or domain.co***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.(?:co|c)\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.com")

    # Pattern 3: domain.n***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.n\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.net")

    # Pattern 4: domain.o***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.o\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.org")

    # Pattern 5: domain.v***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.v\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.vn")

    # Pattern 6: split/masked domains like dawnseeker. .com or site.***.com
    for m in re.finditer(r'([a-zA-Z0-9\-]{3,})\.(?:[\s\*\.\-\_]+)(com|net|org|vn|tw|za\.com|co|site|vip)', clean, re.IGNORECASE):
        p, suf = m.group(1).lower(), m.group(2).lower()
        results.extend([f"{p}.za.{suf}", f"{p}.{suf}", f"{p}.com.{suf}", f"{p}.com", f"{p}.net", f"{p}.org"])

    return list(dict.fromkeys(results))

VALID_TLDS = [
    'com.vn', 'com.tw', 'co.uk', 'co.jp', 'za.com', 'de.com', 'uk.com', 'jpn.com', 'gb.net', 'jp.net', 'cn.com',
    'in.net', 'com.co', 'co.in', 'net.in', 'stridewalk.in', 'org.vn', 'edu.vn', 'pro', 'fun', 'bet', 'asia',
    'com', 'net', 'org', 'io', 'cc', 'me', 'vn', 'tw', 'vip', 'tv', 'co', 'site', 'top', 'online', 'xyz',
    'info', 'biz', 'club', 'games', 'app', 'live', 'ai', 'in', 'us', 'uk'
]
TLD_REGEX = '|'.join([re.escape(t) for t in sorted(VALID_TLDS, key=len, reverse=True)])

def extract_domain_candidates(ocr_lines):
    candidates = []
    raw_texts = []
    for item in (ocr_lines or []):
        if isinstance(item, str):
            t = item.strip()
            if t:
                raw_texts.append(t)
        elif isinstance(item, (list, tuple)) and len(item) > 1:
            t = str(item[1]).strip()
            if t:
                raw_texts.append(t)

    # Synthesize candidates from detected TLDs and distinct words (handles masked SERP snippets)
    all_words = []
    detected_tlds = []
    stopwords = {'http', 'https', 'www', 'link', 'vao', 'cung', 'cap', 'moi', 'nhat', '2026', '2025', 'cho', 'mobile', 'truy', 'nhanh', 'dinh', 'chinh', 'vietnam', 'google', 'search', 'hướng', 'dẫn'}
    for txt in raw_texts:
        for tld in VALID_TLDS:
            if tld in txt.lower() and tld not in detected_tlds:
                detected_tlds.append(tld)
        for w in re.findall(r'[a-zA-Z0-9]+', txt):
            w_l = w.lower()
            if len(w_l) >= 4 and not w_l.isdigit() and w_l not in stopwords:
                all_words.append(w_l)
        # Split PascalCase / camelCase
        for w in re.findall(r'[A-Z][a-z0-9]+', txt):
            wl = w.lower()
            if len(wl) >= 4 and not wl.isdigit() and wl not in stopwords:
                all_words.append(wl)
    all_words = list(dict.fromkeys(all_words))

    # Priority gambling/shortlink TLDs
    priority_tlds = ['com.co', 'com', 'com.vn', 'co', 'in', 'net', 'org', 'in.net', 'top', 'vip']
    for tld in priority_tlds:
        if tld not in detected_tlds:
            detected_tlds.append(tld)

    for tld in detected_tlds:
        for w in all_words:
            if not w.endswith(f".{tld}") and f"{w}.{tld}" not in candidates:
                candidates.append(f"{w}.{tld}")

    # Expand texts with OCR typo corrections
    texts = []
    full_joined = ' '.join(raw_texts)
    raw_texts.append(full_joined)
    # Remove spaces around dots in domain names (e.g. google . com -> google.com)
    joined_domain_parts = re.sub(r'([a-zA-Z0-9\-]+)\s*\.\s*([a-zA-Z0-9\-]+)', r'\1.\2', full_joined)
    raw_texts.append(joined_domain_parts)

    for text in raw_texts:
        texts.append(text)
        fixed = text
        fixed = re.sub(r'\.i0([A-Z])', r'.io \1', fixed)
        fixed = re.sub(r'\.i0(?![a-zA-Z0-9])', '.io', fixed, flags=re.IGNORECASE)
        fixed = re.sub(r'\.c0m(?![a-zA-Z0-9])', '.com', fixed, flags=re.IGNORECASE)
        fixed = re.sub(r'\.0rg(?![a-zA-Z0-9])', '.org', fixed, flags=re.IGNORECASE)
        fixed = re.sub(rf'({TLD_REGEX})([A-Z])', r'\1 \2', fixed)
        if fixed != text:
            texts.append(fixed)

    # Priority 0: Unmask any masked domains like shin-shih.co***.tw or dawnseeker. .com
    for text in texts:
        if any(sym in text for sym in ['*', '★']) or re.search(r'[a-zA-Z0-9\-]{3,}\.\s*(?:\*+)\s*(?:com|net|org|vn)', text):
            for u in unmask_domain_candidates(text):
                if 'link4m' not in u and u not in candidates:
                    candidates.append(u)

    # Priority 1: Match URLs starting with http:// or https:// (allowing trailing path/sub-parts)
    for text in texts:
        for m in re.findall(r'https?:\/\/([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)', text):
            d = m.lower().rstrip('/')
            if 'link4m' not in d and d not in candidates:
                candidates.append(d)

    # Priority 1.5: Stems with explicit protocol (e.g. https://phanvansantos or https://www.ok365)
    EXPAND_TLDS = ['com', 'vn', 'net', 'org', 'com.vn', 'top', 'vip', 'io']
    for text in texts:
        for m in re.finditer(r'https?:\/\/([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*)', text, re.IGNORECASE):
            stem = m.group(1).lower().rstrip('/')
            if 'link4m' not in stem and 'google' not in stem:
                parts = stem.split('.')
                if len(parts) == 1 or (len(parts) == 2 and parts[0] == 'www'):
                    base = parts[-1]
                    for t in EXPAND_TLDS:
                        c1 = f"{base}.{t}"
                        if c1 not in candidates: candidates.append(c1)

    # Priority 2: Match strictly valid TLDs with word boundary (?![a-zA-Z0-9])
    for text in texts:
        for m in re.finditer(rf'\b([a-zA-Z0-9\-]{{2,}}\.(?:{TLD_REGEX}))(?![a-zA-Z0-9])', text, re.IGNORECASE):
            full_d = m.group(1).lower()
            if 'link4m' not in full_d and len(full_d) >= 4 and full_d not in candidates:
                candidates.append(full_d)

    # Priority 3: Match any clean token with dot domain (letters/digits + dot + 2..10 letter TLD)
    for text in texts:
        cleaned = re.sub(r'[^a-zA-Z0-9\.\-\/]', ' ', text)
        for part in cleaned.split():
            part = part.strip('./-')
            m = re.search(rf'^([a-zA-Z0-9\-]+\.(?:{TLD_REGEX}))(?:\/.*)?$', part, re.IGNORECASE)
            if m:
                d = m.group(1).lower().rstrip('/')
                if 'link4m' not in d and len(d) >= 4 and d not in candidates:
                    candidates.append(d)

    url_prefixes = []
    for txt in raw_texts:
        for m in re.finditer(r'https?:\/\/([a-zA-Z0-9\-]+)', txt, re.IGNORECASE):
            p = m.group(1).lower()
            if p not in ['www', 'http', 'https'] and len(p) >= 2:
                url_prefixes.append(p)

    # Phân hạng candidate: ưu tiên tuyệt đối domain có Website: hoặc https:// trong OCR
    def rank_c(c):
        score = 0
        clow = c.lower()
        if 'google' in clow or 'link4m' in clow:
            return -9999
        for p in url_prefixes:
            if clow.startswith(p):
                score += 1000
        for txt in texts:
            tlow = txt.lower().replace(' ', '')
            if f"https://{clow}" in tlow or f"http://{clow}" in tlow or f"website:{clow}" in tlow:
                score += 500
        if clow.count('.') >= 2:
            score += 40
        if any(kw in clow for kw in ['88', 'bet', 'keo', 'cai', 'casino', 'game', 'club', 'slot', 'win']):
            score += 20
        score += len(clow)
        return score

    EXCLUDED_DOMAINS = {'gmail.com', 'gmal.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'mail.com', 'link4m.net', 'link4m.com', 'link4m.org', 'link4m.co', 'link4m.me', 'us.org', 'uk.com', 'us.com', 'vn.com'}
    # Priority 4: Smart OCR self-healing for l <-> i, 1 <-> i / l, 0 <-> o
    ocr_healed = []
    for c in list(candidates):
        variants = set()
        if 'l' in c: variants.add(c.replace('l', 'i'))
        if '1' in c: variants.add(c.replace('1', 'i')); variants.add(c.replace('1', 'l'))
        if '0' in c: variants.add(c.replace('0', 'o'))
        for v in variants:
            if v not in candidates and v not in ocr_healed:
                ocr_healed.append(v)
    candidates.extend(ocr_healed)

    candidates = [c for c in candidates if 'google' not in c.lower() and 'link4m' not in c.lower() and c.lower() not in EXCLUDED_DOMAINS and len(c.split('.')[0]) >= 3]
    candidates.sort(key=rank_c, reverse=True)
    return candidates

from concurrent.futures import ThreadPoolExecutor

def _probe_single_proto(proto_url: str):
    try:
        req = urllib.request.Request(
            proto_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=2.5) as resp:
            if resp.getcode() in (200, 301, 302):
                final_url = resp.geturl() if resp.geturl() else proto_url
                final_url = final_url.rstrip('/')
                html = resp.read(65536).decode('utf-8', errors='ignore')
                has_script = any(k in html.lower() for k in ['traffic', 'widget', 'what-on', 'website-analytics', 'service-v', 'lấy mã', 'lay ma'])
                return (final_url, has_script)
    except Exception:
        pass
    return ("", False)

def resolve_ip_google(domain: str) -> str:
    try:
        url = f"https://dns.google/resolve?name={domain}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=1.5) as r:
            import json
            data = json.loads(r.read())
            for ans in data.get('Answer', []):
                if ans.get('type') == 1:
                    return ans['data']
    except Exception:
        pass
    return ""

def probe_domain_live(domain: str):
    targets = [f"https://{domain}", f"http://{domain}"]
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(_probe_single_proto, t) for t in targets]
        best_url = ""
        has_best_script = False
        for f in futures:
            res_url, has_sc = f.result()
            if res_url:
                if has_sc:
                    return (res_url, True)
                if not best_url:
                    best_url = res_url
        if best_url:
            return (best_url, has_best_script)
    ip = resolve_ip_google(domain)
    if ip:
        return (f"https://{domain}", True)
    return ("", False)

def detect_sponsor_domain(page_link):
    all_texts = []
    base64_images = []

    # Step 1: Extract from Link4M page DOM text directly
    try:
        page_text = page_link.locator("body").inner_text()
        all_texts.extend(page_text.splitlines())
    except Exception:
        pass

    # Step 2: Extract from target sponsor images and base64 images
    log("[*] Đang quét hình ảnh quảng cáo & hướng dẫn nhiệm vụ...")
    for _ in range(8):
        try:
            imgs_info = page_link.evaluate("""() => {
                const res = [];
                document.querySelectorAll('img').forEach(img => {
                    const s = img.src || '';
                    if (s.startsWith('data:image/')) {
                        res.push({ type: 'b64', src: s });
                    } else if (s.includes('img.link4m.net') || s.includes('advertiser') || /\\d+_\\d+\\.(?:jpg|png)/.test(s)) {
                        res.push({ type: 'url', src: s });
                    }
                });
                return res;
            }""")
            if imgs_info:
                break
        except Exception:
            pass
        time.sleep(0.2)

    log(f"[*] Phát hiện {len(imgs_info or [])} ảnh nhiệm vụ. Đang chạy Cloud OCR API siêu tốc song song...")
    def _fetch_one_img(item):
        try:
            if item['type'] == 'b64':
                b64_str = item['src'].split(',', 1)[1] if ',' in item['src'] else item['src']
                return base64.b64decode(b64_str)
            else:
                req = urllib.request.Request(item['src'], headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://link4m.net/'})
                with urllib.request.urlopen(req, context=_SSL_CTX, timeout=3.5) as r:
                    return r.read()
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=min(len(imgs_info or [1]), 5)) as ex:
        all_img_bytes = list(ex.map(_fetch_one_img, imgs_info or []))

    # Phase 1: High-speed parallel Cloud OCR API (3s)
    cloud_texts = []
    valid_imgs = [b for b in all_img_bytes if b]
    if valid_imgs:
        with ThreadPoolExecutor(max_workers=min(len(valid_imgs), 5)) as ex:
            cloud_results = list(ex.map(_ocr_cloud_api, valid_imgs))
        for c_res in cloud_results:
            if c_res:
                cloud_texts.extend(c_res.splitlines())

    candidates = extract_domain_candidates(all_texts + cloud_texts)

    # Phase 2: Automatic Fallback to Local RapidOCR if Cloud API returned no viable candidates
    if not candidates and valid_imgs:
        log("[!] Cloud OCR chưa đủ dữ liệu, tự động kích hoạt Local RapidOCR AI...")
        ocr = get_ocr()
        for idx_img, img_bytes in enumerate(valid_imgs):
            try:
                res, _ = ocr(img_bytes)
                if res:
                    for line in res:
                        if len(line) > 1:
                            all_texts.append(line[1].strip())
                    try:
                        items = []
                        for box, text, conf in res:
                            cy = (box[0][1] + box[2][1]) / 2.0
                            min_x = min(p[0] for p in box)
                            items.append((cy, min_x, text))
                        items.sort(key=lambda x: x[0])
                        clusters = []
                        for it in items:
                            if not clusters or abs(clusters[-1][0] - it[0]) > 15:
                                clusters.append([it[0], [it]])
                            else:
                                clusters[-1][1].append(it)
                        for _, box_list in clusters:
                            box_list.sort(key=lambda x: x[1])
                            c_line = ' '.join(b[2] for b in box_list)
                            all_texts.append(c_line)
                    except Exception:
                        pass
            except Exception:
                pass
        candidates = extract_domain_candidates(all_texts)
    else:
        all_texts.extend(cloud_texts)
        log(f"[+] Cloud OCR hoàn tất siêu tốc ({len(cloud_texts)} dòng chữ trích xuất).")

    brain = get_brain()
    candidates = brain.prioritize_candidates(candidates)
    log(f"[*] Trích xuất {len(candidates)} tên miền ứng viên (sau khi lọc Brain & giải mã mask): {candidates}")

    # Sắp xếp và phân hạng các ứng viên:
    def rank_candidate(c):
        score = 0
        clow = c.lower()
        prof = brain.get_domain_profile(clow)
        if prof and prof.get("success_count", 0) > 0:
            score += 1000 + prof.get("success_count", 0) * 50
        for txt in all_texts:
            tlow = txt.lower()
            if f"https://{clow}" in tlow or f"http://{clow}" in tlow or f"website:{clow}" in tlow.replace(' ', ''):
                score += 500
        if clow.count('.') >= 2:
            score += 40
        if any(kw in clow for kw in ['88', 'bet', 'keo', 'cai', 'casino', 'game', 'club', 'slot', 'win']):
            score += 20
        prefix = clow.split('.')[0]
        if len(prefix) <= 3 and not prefix.isdigit():
            score -= 15
        score += len(clow) * 0.1
        return score

    candidates.sort(key=rank_candidate, reverse=True)

    log(f"[*] Đang kiểm tra kết nối & DNS live probe cho các ứng viên...")
    # Probe live domain: domains with verified active sponsor scripts get TOP priority!
    script_urls = []
    live_urls = []
    for c in candidates:
        live_url, has_sc = probe_domain_live(c)
        if live_url:
            if has_sc and live_url not in script_urls:
                script_urls.append(live_url)
            elif live_url not in live_urls:
                live_urls.append(live_url)

    final_live = script_urls + [u for u in live_urls if u not in script_urls]
    if final_live:
        log(f"[+] Verified live sponsor website candidates (priority sorted): {final_live}")
        return final_live

    # If Cloud OCR returned candidates but NONE were live, trigger Local RapidOCR
    if valid_imgs and (not candidates or not final_live):
        log("[*] Không tìm thấy ứng viên live từ Cloud OCR, kích hoạt Local RapidOCR để quét lại ảnh...")
        ocr = get_ocr()
        local_texts = []
        for idx_img, img_bytes in enumerate(valid_imgs):
            try:
                res, _ = ocr(img_bytes)
                if res:
                    for line in res:
                        if len(line) > 1:
                            local_texts.append(line[1].strip())
            except Exception:
                pass
        candidates_local = extract_domain_candidates(local_texts)
        candidates_local = brain.prioritize_candidates(candidates_local)
        candidates_local.sort(key=rank_candidate, reverse=True)
        log(f"[*] Trích xuất ứng viên từ RapidOCR: {candidates_local}")
        for c in candidates_local:
            live_url, has_sc = probe_domain_live(c)
            if live_url:
                if has_sc and live_url not in script_urls:
                    script_urls.append(live_url)
                elif live_url not in live_urls:
                    live_urls.append(live_url)
        final_live = script_urls + [u for u in live_urls if u not in script_urls]
        if final_live:
            log(f"[+] Verified live sponsor website candidates từ Local RapidOCR: {final_live}")
            return final_live

    if candidates:
        fallbacks = [f"https://{c}" for c in candidates if not brain.is_blacklisted(c) and resolve_ip_google(c)]
        if fallbacks:
            log(f"[+] Fallback to candidate list: {fallbacks}")
            return fallbacks

    return []

def _solve_single_sponsor(context, sponsor_url: str) -> str:
    t_single_start = time.time()
    log(f"[*] Opening sponsor site via Google referrer: {sponsor_url}")
    page = context.new_page()

    def on_sponsor_popup(p):
        if p != page:
            try:
                p.close()
            except Exception:
                pass
    context.on("page", on_sponsor_popup)

    try:
        return _solve_single_sponsor_impl(context, page, sponsor_url, t_single_start)
    finally:
        try:
            context.remove_listener("page", on_sponsor_popup)
        except Exception:
            pass
        try:
            page.close()
        except Exception:
            pass

def _solve_single_sponsor_impl(context, page, sponsor_url: str, t_single_start: float) -> str:
    code_from_api = False

    # 1. Neutralize detectIncognito cleanly
    page.add_init_script("""
        if (window.navigator && window.navigator.webkitTemporaryStorage) {
            window.navigator.webkitTemporaryStorage.queryUsageAndQuota = function(success, error) {
                if (typeof success === 'function') success(100, 100000000000);
            };
        }
        window.mouse_scroll = true;
        window.traffic_click = true;
    """)

    def route_handler(route):
        req = route.request
        if req.resource_type in ["image", "media", "font"]:
            route.abort()
            return
        u = req.url.lower()
        if any(ep in u for ep in ["get_quest_code", "get_code", "ajax_code", "lay_ma", "process-site", "check-site", "iatum"]):
            route.continue_()
            return
        if any(k in u for k in ["service", "widget", "traffic", "what-on", "website-analytics", "yoads"]) and (".js" in u or "script" in req.resource_type):
            try:
                res = route.fetch()
                body = res.text()
                # 1. Bypass detectIncognito at root definition
                body = re.sub(r'if\s*\(\s*result\.isPrivate\s*\)\s*\{', 'if(false){', body)
                body = re.sub(r'function\s+__callback\s*\(\s*isPrivate\s*\)\s*\{', 'function __callback(isPrivate) { isPrivate = false; ', body)
                body = body.replace('async function detectIncognito() {', 'async function detectIncognito() { return { isPrivate: false, browserName: "Chrome" }; } async function _old_detectIncognito() {')
                body = body.replace('var detectIncognito = async function () {', 'var detectIncognito = async function () { return { isPrivate: false, browserName: "Chrome" }; }; var _old_detectIncognito = async function () {')
                body = body.replace('if(result.isPrivate){', 'if(false){')
                body = re.sub(r'var check_ref\s*=\s*false;', 'var check_ref = true;', body)

                # 2. Keep scroll/active state & eliminate blur lock (handles CRLF and tabs)
                body = re.sub(r'!\s*mouse_scroll', 'false', body)
                body = re.sub(r'mouse_scroll\s*=\s*[^;]+;', 'mouse_scroll = true;', body)
                body = re.sub(r'traffic_blurred\s*\|\|', '', body)
                body = re.sub(r'var\s+traffic_blurred\s*=\s*[^;]+;', 'var traffic_blurred = false;', body)
                body = re.sub(r'traffic_blurred\s*=\s*[^;]+;', 'traffic_blurred = false;', body)
                body = re.sub(r'mouse_scroll_time\s*\+\s*delay_time\s*<\s*Date\.now\(\)\s*\/\s*1000\s*&&\s*\([^)]*\)', 'false', body)

                # 3. Expose checkButtonClick to window
                body = body.replace('function checkButtonClick(){', 'window.__checkButtonClick = checkButtonClick; function checkButtonClick(){')

                # 4. Universal quest_info fallback across all steps and domains
                quest_patch = """var quest_info = localStorage.getItem(uuid_name + '_quest');
if (!quest_info && typeof(Storage) !== "undefined") {
    for (var _k in localStorage) {
        if (_k.includes('quest')) {
            try {
                var _tmp = JSON.parse(localStorage.getItem(_k));
                if (_tmp && _tmp.id) { quest_info = localStorage.getItem(_k); localStorage.setItem(uuid_name + '_quest', quest_info); break; }
            } catch(e) {}
        }
    }
}"""
                body = body.replace("var quest_info = localStorage.getItem(uuid_name + '_quest');", quest_patch)

                route.fulfill(response=res, body=body)
                return
            except Exception:
                pass
        route.continue_()

    page.route("**/*", route_handler)
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        if (window.navigator && window.navigator.webkitTemporaryStorage) {
            window.navigator.webkitTemporaryStorage.queryUsageAndQuota = (s) => { if (typeof s === 'function') s(0, 500*1024*1024*1024); };
        }
        window.detectIncognito = () => Promise.resolve({ isPrivate: false, browserName: "Chrome" });
        try {
            Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
            Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
            window.hasFocus = () => true;
        } catch (e) {}
    """)

    try:
        page.goto(sponsor_url, wait_until="domcontentloaded", referer="https://www.google.com/", timeout=40000)
    except Exception as e:
        if "ERR_NAME_NOT_RESOLVED" in str(e):
            d_name = urllib.parse.urlparse(sponsor_url).netloc.split(':')[0]
            ip = resolve_ip_google(d_name)
            if ip:
                log(f"[*] DNS self-healing: Domain {d_name} resolved to {ip} via Google DNS. Spawning mapped session...")
                try: page.close()
                except Exception: pass
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p_sub:
                        b_sub = p_sub.chromium.launch(
                            headless=True,
                            args=[
                                f'--host-resolver-rules=MAP {d_name} {ip}, MAP *.{d_name} {ip}, MAP s1.what-on.com 104.21.43.112, MAP what-on.com 172.67.178.139',
                                '--no-sandbox'
                            ]
                        )
                        ctx_sub = b_sub.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                            viewport={"width": 1280, "height": 720}
                        )
                        res_code = _solve_single_sponsor(ctx_sub, sponsor_url)
                        b_sub.close()
                        return res_code
                except Exception as sub_e:
                    log(f"[!] Mapped session error: {sub_e}")
        log(f"[!] Sponsor goto note: {e}")
        try: page.close()
        except Exception: pass
        return None
    time.sleep(0.4)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        html = page.content()
    except Exception:
        try:
            time.sleep(1)
            html = page.content()
        except Exception:
            html = ""
    m_key = re.search(r'(?:what-on\.com|website-analytics\.net|traffic)[^"\']*?key=([a-zA-Z0-9]+)', html)
    traffic_key = m_key.group(1) if m_key else None
    if not traffic_key:
        layout_blacklist = {'masthead', 'colophon', 'comments', 'site-nav', 'primary', 'secondary', 'content', 'wrapper', 'sidebar', 'footer', 'header', 'main-menu', 'wide-nav'}
        div_ids = page.evaluate("""() => Array.from(document.querySelectorAll('div[id]'))
            .map(d => d.id)
            .filter(id => (/^[a-zA-Z0-9]{8}$/.test(id) || /countdown|traffic|layma/i.test(id)))
        """)
        div_ids = [i for i in (div_ids or []) if i.lower() not in layout_blacklist]
        if div_ids:
            traffic_key = div_ids[0]
    log(f"[*] Detected traffic_key: {traffic_key}")

    def clean_code_str(text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r'<[^>]+>', '', str(text))
        clean = re.sub(r'^(?:M[ãa]\s*KM|M[ãa]\s*x[áa]c\s*nh[ậa]n|Code|M[ãa])[\s\:\-]+', '', clean, flags=re.IGNORECASE)
        lines = [l.strip() for l in clean.splitlines() if l.strip()]
        clean = lines[0] if lines else ""
        clean = re.sub(r'[\s\:\.\,\!\?]+$', '', clean)
        return clean.strip()

    def is_valid_sponsor_code(text: str) -> bool:
        t = clean_code_str(text)
        if not t or len(t) < 4 or len(t) > 25:
            return False
        if any(w in t.lower() for w in ['click', 'vui lòng', 'vui long', 'link', 'bước', 'buoc', 'lay ma', 'lấy mã', 'chờ', 'seconds', 'giây', 'loading']):
            return False
        return bool(re.match(r'^[A-Za-z0-9_\-]{4,25}$', t))

    code_found = None
    campaign_dead = False
    def on_resp(res):
        nonlocal code_found, campaign_dead, code_from_api
        u_lower = res.url.lower()
        if any(ep in u_lower for ep in ["get_quest_code", "get_code", "ajax_code", "lay_ma", "process-code", "process-site", "check-site", "iatum", "ontops"]):
            try:
                data = None
                try:
                    data = res.json()
                except Exception:
                    data = None

                if isinstance(data, dict):
                    log(f"[*] API Response JSON from {res.url[:70]}: {data}")
                    if data.get("info") == "No Campaign" or (data.get("success") is False and "No Campaign" in str(data)):
                        campaign_dead = True
                    raw = data.get("html") or data.get("code") or data.get("data") or data.get("c")
                    if raw:
                        val = clean_code_str(raw)
                        if is_valid_sponsor_code(val):
                            code_found = val
                            code_from_api = True
                            log(f"🎉 EXTRACTED SPONSOR CODE FROM API: {code_found}")
                            return
                        else:
                            log(f"[*] API intermediate message: {val}")

                # Text / Regex fallback
                try:
                    txt = res.text()
                    if txt and len(txt) < 5000:
                        m = re.search(r'(?:M[ãa]\s*KM|code|m[ãa])[\s":=\-]+([A-Za-z0-9_\-]{4,25})', txt, re.IGNORECASE)
                        if m:
                            val = clean_code_str(m.group(1))
                            if is_valid_sponsor_code(val):
                                code_found = val
                                code_from_api = True
                                log(f"🎉 EXTRACTED SPONSOR CODE FROM API TEXT: {code_found}")
                                return
                except Exception:
                    pass
            except Exception:
                pass
    page.on("response", on_resp)

    def get_button_selectors(tk):
        sel_list = []
        if tk:
            sel_list.extend([
                f"[id='{tk}'] button",
                f"[id='{tk}'] a",
                f"[id='{tk}'] [role='button']",
                f"[id='{tk}']",
                f"[data-key='{tk}']",
                f"#ss-{tk}",
            ])
        sel_list.extend([
            "#traffic-button", ".traffic-button", "[class*='traffic-button']", "[id*='traffic-button']",
            ".traffic-button__content", "#traffic-button__content",
            ".whatoncode", "[class*='whatoncode']", "[id*='whatoncode']",
            "[class*='btn-traffic']", "[id*='btn-traffic']", "[class*='traffic-btn']",
            "[class*='btn-layma']", "[id*='btn-layma']", "[class*='layma']", "[id*='layma']",
            "[class*='lay-ma']", "[id*='lay-ma']", "[class*='btn-lay-ma']",
            "[class*='getcode']", "[id*='getcode']", "[class*='get-code']", "[id*='get-code']",
            "[class*='lay-code']", "[id*='lay-code']",
            "button:has-text('LẤY MÃ')", "a:has-text('LẤY MÃ')", "div:has-text('LẤY MÃ')", "span:has-text('LẤY MÃ')",
            "button:has-text('LAY MA')", "a:has-text('LAY MA')", "div:has-text('LAY MA')",
            "button:has-text('LẤY CODE')", "a:has-text('LẤY CODE')", "div:has-text('LẤY CODE')",
            "button:has-text('GET CODE')", "a:has-text('GET CODE')", "div:has-text('GET CODE')",
            "button:has-text('NHẬN MÃ')", "a:has-text('NHẬN MÃ')", "div:has-text('NHẬN MÃ')",
            "button:has-text('LẤY PASS')", "a:has-text('LẤY PASS')",
            "button:has-text('LẤY KEY')", "a:has-text('LẤY KEY')",
            "button:has-text('BẤM VÀO ĐÂY')", "a:has-text('BẤM VÀO ĐÂY')",
            "button:has-text('XEM MÃ')", "a:has-text('XEM MÃ')",
            "button:has-text('TIẾP TỤC')", "a:has-text('TIẾP TỤC')",
            "button:has-text('CONTINUE')", "a:has-text('CONTINUE')",
            ".completed", "[class*='completed']",
            "[data-traffic]", "[data-quest]", "[data-code]"
        ])
        return sel_list

    def find_mission_button(timeout_sec=5.0):
        nonlocal traffic_key
        start_t = time.time()
        while time.time() - start_t < timeout_sec:
            if not traffic_key:
                try:
                    dyn_k = page.evaluate("""() => {
                        if (window.traffic_key) return window.traffic_key;
                        if (window.whaton_key) return window.whaton_key;
                        for (let k in localStorage) {
                            if (k.includes('quest') || k.includes('traffic')) {
                                try {
                                    const v = JSON.parse(localStorage.getItem(k));
                                    if (v && (v.key || v.id)) return v.key || v.id;
                                } catch (e) {}
                            }
                        }
                        const el = document.querySelector('[data-key], [id*="traffic-button"], .whatoncode, [class*="whatoncode"]');
                        if (el) return el.dataset.key || el.id || null;
                        return null;
                    }""")
                    if dyn_k:
                        traffic_key = str(dyn_k)
                        log(f"[*] Dynamically identified traffic_key: {traffic_key}")
                except Exception:
                    pass

            selectors = get_button_selectors(traffic_key)
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        return loc
                except Exception:
                    pass

            try:
                js_matched = page.evaluate("""() => {
                    const textRegex = /l[ấa]y\\s*m[ãa]|lay\\s*ma|get\\s*code|nh[ậa]n\\s*m[ãa]|l[ấa]y\\s*pass|l[ấa]y\\s*key|click\\s*v[àa]o\\s*đ[âa]y|b[ấa]m\\s*v[àa]o\\s*đ[âa]y|nh[ậa]n\\s*code/i;
                    const candidates = document.querySelectorAll('button, a, div, span, p, [role="button"]');
                    for (const el of candidates) {
                        if (el.children.length > 5) continue;
                        const txt = (el.innerText || el.textContent || '').trim();
                        if (txt && txt.length < 50 && textRegex.test(txt)) {
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            el.setAttribute('data-link4m-matched', 'true');
                            return true;
                        }
                    }
                    const w = document.querySelector('.whatoncode, [class*="whatoncode"], #traffic-button, .traffic-button, [class*="traffic-button"]');
                    if (w) {
                        w.scrollIntoView({ behavior: 'instant', block: 'center' });
                        w.setAttribute('data-link4m-matched', 'true');
                        return true;
                    }
                    return false;
                }""")
                if js_matched:
                    loc = page.locator("[data-link4m-matched='true']").first
                    if loc.count() > 0:
                        return loc
            except Exception:
                pass

            elapsed = time.time() - start_t
            frac = min(1.0, elapsed / timeout_sec)
            try:
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {frac});")
            except Exception:
                pass
            time.sleep(0.4)
        return None

    def prep():
        for _ in range(3):
            try:
                page.evaluate(f"""() => {{
                    document.querySelectorAll('script[type="rocketlazyloadscript"]').forEach(s => {{
                        const ns = document.createElement('script');
                        if (s.hasAttribute('data-rocket-src')) {{
                            let src = s.getAttribute('data-rocket-src');
                            ns.src = src.startsWith('//') ? 'https:' + src : src;
                        }} else {{
                            ns.textContent = s.textContent;
                        }}
                        document.body.appendChild(ns);
                    }});
                    document.querySelectorAll('#hpps-popup, .hpps-popup, .popup, .modal, [class*="popup"]').forEach(e => e.remove());
                    if ('{traffic_key}') {{
                        window.location.hash = '#ss-{traffic_key}';
                        if (typeof forceShowButton === 'function') forceShowButton();
                    }}
                    window.scrollTo(0, document.body.scrollHeight);

                    // Active scroll heartbeat to defeat mouse_scroll timer pause in service-v3.js
                    if (!window.heartbeat_scroll) {{
                        let dir = 1;
                        window.heartbeat_scroll = setInterval(() => {{
                            window.scrollBy(0, 25 * dir);
                            dir = -dir;
                            window.dispatchEvent(new Event('scroll'));
                        }}, 750);
                    }}
                }}""")
                break
            except Exception:
                time.sleep(0.5)

    visited = {sponsor_url.rstrip("/")}
    for step in range(1, 3):
        if code_found or campaign_dead:
            break
        log(f"\n[*] EXECUTING STEP {step} ON SPONSOR SITE")

        if step > 1:
            article = None
            try:
                article_candidates = page.evaluate("""(sp_url) => {
                    const links = [];
                    // 1. Direct Step 2 link injected into whatoncode / completed button by widget
                    const questLink = document.querySelector('.whatoncode a[href], .whatoncode-wrapper a[href], .completed a[href], [class*="whatoncode"] a[href]');
                    if (questLink && questLink.href && !questLink.href.startsWith('javascript:')) {
                        const cleanLink = questLink.href.split('#')[0].replace(/\\/$/, '');
                        if (!cleanLink.includes('tracking') && !cleanLink.includes('tracker')) {
                            links.push(cleanLink);
                        }
                    }
                    // 2. Scan on-page article links with matching hostname
                    const host = new URL(sp_url).hostname.replace(/^www\\./, '').toLowerCase();
                    document.querySelectorAll('a[href]').forEach(a => {
                        try {
                            const u = new URL(a.href, window.location.href);
                            const uHost = u.hostname.replace(/^www\\./, '').toLowerCase();
                            if (uHost === host && u.pathname.length > 2 && !u.pathname.includes('wp-admin') && !u.pathname.includes('feed') && !u.href.includes('#') && !u.pathname.includes('tracking') && !u.pathname.includes('cdn-cgi')) {
                                links.push(u.href.replace(/\\/$/, ''));
                            }
                        } catch (e) {}
                    });
                    return Array.from(new Set(links));
                }""", sponsor_url)
                for cand in (article_candidates or []):
                    if cand not in visited and not any(cand.endswith(ext) for ext in [".jpg", ".png", ".webp", ".css", ".js", ".svg"]):
                        article = cand
                        visited.add(cand)
                        break
            except Exception:
                pass
            if not article or article == sponsor_url:
                article = sponsor_url.rstrip("/")
                sep = "&" if "?" in article else "?"
                art_url = f"{article}{sep}step={step}#ss-{traffic_key}" if traffic_key else f"{article}{sep}step={step}"
            else:
                art_url = f"{article}#ss-{traffic_key}" if traffic_key and "#" not in article else article
            log(f"[*] Navigating to Step {step} article: {art_url}")
            try:
                resp = page.goto(art_url, wait_until="domcontentloaded", timeout=35000)
                if resp and resp.status in (404, 500, 502, 503):
                    log(f"[!] Article {art_url} returned {resp.status}, trying fallback article...")
                    for fallback_cand in (article_candidates or []):
                        if fallback_cand not in visited and fallback_cand != cand:
                            art_url = f"{fallback_cand}#ss-{traffic_key}" if traffic_key else fallback_cand
                            visited.add(fallback_cand)
                            log(f"[*] Fallback navigating to Step {step} article: {art_url}")
                            resp2 = page.goto(art_url, wait_until="domcontentloaded", timeout=35000)
                            if resp2 and resp2.status not in (404, 500, 502, 503):
                                break
            except Exception:
                pass
            time.sleep(1.5)

        prep()
        time.sleep(0.5)

        btn = find_mission_button(timeout_sec=4.5)
        if (not btn or btn.count() == 0) and step == 1:
            log(f"[*] Step 1: Nút chưa xuất hiện trên trang đích, đang tìm bài viết nội bộ trên {sponsor_url}...")
            try:
                art_candidates = page.evaluate("""(sp_url) => {
                    const host = new URL(sp_url).hostname.replace(/^www\\./, '').toLowerCase();
                    const links = [];
                    const selectors = [
                        'article a[href]', '.post a[href]', '.entry-title a[href]',
                        'main a[href]', 'h1 a[href]', 'h2 a[href]', 'h3 a[href]',
                        '.news-item a[href]', '.blog-item a[href]', '.content a[href]',
                        'a[href]'
                    ];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(a => {
                            try {
                                const u = new URL(a.href, window.location.href);
                                const uHost = u.hostname.replace(/^www\\./, '').toLowerCase();
                                if (uHost === host && u.pathname.length > 3) {
                                    const path = u.pathname.toLowerCase();
                                    if (!path.includes('wp-admin') && !path.includes('login') && !path.includes('register')
                                        && !path.includes('tag') && !path.includes('category') && !path.includes('page')
                                        && !path.includes('feed') && !path.includes('contact') && !path.includes('about')
                                        && !path.includes('policy') && !path.includes('terms') && !u.href.includes('#')) {
                                        links.push(u.href.replace(/\\/$/, ''));
                                    }
                                }
                            } catch (e) {}
                        });
                        if (links.length >= 5) break;
                    }
                    return Array.from(new Set(links));
                }""", sponsor_url)
                if art_candidates:
                    log(f"[*] Tìm thấy {len(art_candidates)} bài viết tiềm năng. Thử truy cập bài viết đầu tiên: {art_candidates[0]}")
                    try:
                        page.goto(art_candidates[0], wait_until="domcontentloaded", timeout=35000)
                        time.sleep(1.0)
                        prep()
                        btn = find_mission_button(timeout_sec=5.0)
                    except Exception as ea:
                        log(f"[!] Article nav error: {ea}")
            except Exception:
                pass

        if not btn or btn.count() == 0:
            log(f"[!] Step {step}: Button not found after exhaustive scan, skipping...")
            if step == 1 and not traffic_key:
                log(f"[!] Bước 1 không tìm thấy nút nhiệm vụ trên cả trang chủ lẫn bài viết, chuyển ứng viên khác.")
                try: page.close()
                except Exception: pass
                return None
            continue

        log(f"[+] Step {step}: Button located. Clicking...")
        try:
            btn.scroll_into_view_if_needed(timeout=2000)
            btn.click(force=True, timeout=2500)
        except Exception:
            try:
                btn.evaluate("el => el.click()")
            except Exception:
                pass
        page.evaluate("""() => {
            if (typeof window.__checkButtonClick === 'function') window.__checkButtonClick();
            else if (typeof checkButtonClick === 'function') checkButtonClick();
            else if (typeof startCountdown === 'function') startCountdown();
        }""")
        time.sleep(0.4)

        sec_dur = page.evaluate(f"""() => {{
            if (typeof counter2 !== 'undefined' && counter2 !== null && counter2 > 0) return parseFloat(counter2);
            const el = document.getElementById('{traffic_key}');
            if (el && el.dataset.time) return parseFloat(el.dataset.time);
            const whaton = document.querySelector('.whatoncode, [class*="whatoncode"]');
            if (whaton) {{
                const m = (whaton.innerText || whaton.textContent || '').match(/(\\d+)\\s*(?:giây|s)/i);
                if (m) return parseFloat(m[1]);
            }}
            const tfBtn = document.querySelector('#traffic-button, .traffic-button');
            if (tfBtn) {{
                const m = (tfBtn.innerText || '').match(/(\\d+)\\s*(?:giây|s)/i);
                if (m) return parseFloat(m[1]);
            }}
            return (typeof traffic_step_2_wait_time !== 'undefined' && {step} > 1 ? traffic_step_2_wait_time : ({step} > 1 ? 15 : 60));
        }}""")
        log(f"[*] Step {step}: Countdown duration = {sec_dur}s")

        dir_wheel = 1
        start_step_time = time.time()
        max_ticks = int((sec_dur + 35) * 2)
        for tick in range(1, max(max_ticks, 60)):
            time.sleep(0.5)
            if tick % 3 == 0:
                dir_wheel = -dir_wheel
                try: page.mouse.wheel(0, 120 * dir_wheel)
                except Exception: pass

            rem = page.evaluate(f"""() => {{
                if (typeof counter2 !== 'undefined' && counter2 !== null) return parseFloat(counter2);
                const whaton = document.querySelector('.whatoncode, [class*="whatoncode"]');
                if (whaton) {{
                    const text = whaton.innerText || whaton.textContent || '';
                    if (text.includes('Mã KM:') || text.includes('Mã:')) return 0.0;
                    const m = text.match(/(\\d+)\\s*s\\s*\\(/i) || text.match(/(\\d+)\\s*(?:giây|s)/i);
                    if (m) return parseFloat(m[1]);
                }}
                const el = document.getElementById('{traffic_key}');
                if (el && el.dataset.time) return parseFloat(el.dataset.time);
                const btn = document.querySelector("#traffic-button, .traffic-button, .completed, [class*='completed'], [id='{traffic_key}'] button, [id='{traffic_key}'], button");
                if (btn) {{
                    const m = (btn.innerText || '').match(/(\\d+)\\s*(?:giây|s)/i);
                    if (m) return parseFloat(m[1]);
                }}
                return null;
            }}""")
            if rem is None:
                elapsed = time.time() - start_step_time
                rem = max(0.0, sec_dur - elapsed)

            if rem is not None:
                if tick % 6 == 0 or rem <= 3:
                    log(f"  [Step {step}] Remaining: {int(rem)}s")
                if rem <= 0:
                    page.evaluate(f"""() => {{
                        const el = document.getElementById('{traffic_key}');
                        if (el) {{
                            el.dataset.time = '0';
                            el.dataset.click = 'true';
                            if (el.dataset.loading !== 'true' && el.dataset.loaded === undefined) {{
                                if (typeof window.__checkButtonClick === 'function') {{
                                    window.__checkButtonClick();
                                }} else if (typeof checkButtonClick === 'function') {{
                                    checkButtonClick();
                                }}
                            }}
                        }}
                    }}""")
                    try:
                        page.evaluate(f"""() => {{
                            const el = document.getElementById('{traffic_key}');
                            if (!el || el.dataset.loading !== 'true') {{
                                const btn = document.querySelector(".whatoncode, [id='{traffic_key}'] button, [id='{traffic_key}'] a, .completed");
                                if (btn && (!btn.innerText || !btn.innerText.includes('Mã KM'))) btn.click();
                            }}
                        }}""")
                    except Exception:
                        pass
                    if step == 1:
                        # Kiểm tra xem mã có xuất hiện luôn ở bước 1 không (single-step sponsor / traffic.com.vn)
                        for _ in range(16):
                            time.sleep(0.5)
                            if code_found:
                                break
                            try:
                                dom_t = page.evaluate(f"""() => {{
                                    const tfBtn = document.querySelector('#traffic-button, .traffic-button, .traffic-button__content');
                                    if (tfBtn) {{
                                        const text = tfBtn.innerText || tfBtn.textContent || '';
                                        const m = text.match(/(?:M[ãa]\\s*KM|M[ãa]\\s*x[áa]c\\s*nh[ậa]n|Code|M[ãa])[\\s\\:\\-]+([A-Za-z0-9_\\-]{{4,25}})/i);
                                        if (m) return m[1];
                                        const t = text.trim();
                                        if (/^[A-Za-z0-9_\\-]{{4,25}}$/.test(t) && !/lay|ma|click|link|buoc|cho|wait|giay|second|loading|keo/i.test(t)) return t;
                                    }}
                                    const el = document.getElementById('{traffic_key}');
                                    if (el) {{
                                        const d = el.getElementsByTagName('div')[0];
                                        if (d && d.innerText) return d.innerText;
                                        return el.dataset.code || el.value || el.innerText || '';
                                    }}
                                    const cBtn = document.querySelector('.completed, [class*="completed"]');
                                    if (cBtn && cBtn.innerText) return cBtn.innerText;
                                    return null;
                                }}""")
                                if dom_t:
                                    cleaned = clean_code_str(dom_t)
                                    if is_valid_sponsor_code(cleaned):
                                        code_found = cleaned
                                        log(f"🎉 EXTRACTED SPONSOR CODE FROM DOM IN STEP 1: {code_found}")
                                        break
                            except Exception:
                                pass
                            has_quest = page.evaluate(f"() => {{ for (let k in localStorage) {{ if (k.includes('quest')) return true; }} return false; }}")
                            if has_quest:
                                break
                    else:
                        log(f"[*] Step {step} countdown finished! Waiting for mission code from API/DOM...")
                        for wait_i in range(50):
                            time.sleep(0.5)
                            if code_found:
                                break
                            if wait_i % 3 == 0:
                                try:
                                    page.mouse.wheel(0, 100 if wait_i % 6 == 0 else -100)
                                    page.evaluate("""() => {
                                        if (typeof window.__checkButtonClick === 'function') window.__checkButtonClick();
                                        else if (typeof checkButtonClick === 'function') checkButtonClick();
                                        const c = document.querySelector('.whatoncode, .completed, button');
                                        if (c && (!c.innerText || !c.innerText.includes('Mã KM'))) c.click();
                                    }""")
                                except Exception:
                                    pass
                            try:
                                dom_t = page.evaluate(f"""() => {{
                                    // 0. Check traffic-button / best-traffic
                                    const tfBtn = document.querySelector('#traffic-button, .traffic-button, .traffic-button__content');
                                    if (tfBtn) {{
                                        const text = tfBtn.innerText || tfBtn.textContent || '';
                                        const m = text.match(/(?:M[ãa]\\s*KM|M[ãa]\\s*x[áa]c\\s*nh[ậa]n|Code|M[ãa])[\\s\\:\\-]+([A-Za-z0-9_\\-]{{4,25}})/i);
                                        if (m) return m[1];
                                        const t = text.trim();
                                        if (/^[A-Za-z0-9_\\-]{{4,25}}$/.test(t) && !/lay|ma|click|link|buoc|cho|wait|giay|second|loading|keo/i.test(t)) return t;
                                    }}
                                    // 1. Check whatoncode
                                    const whaton = document.querySelector('.whatoncode, [class*="whatoncode"], .whatoncode-wrapper');
                                    if (whaton) {{
                                        const text = whaton.innerText || whaton.textContent || '';
                                        const m = text.match(/(?:M[ãa]\\s*KM|M[ãa]\\s*x[áa]c\\s*nh[ậa]n|Code|M[ãa])[\\s\\:\\-]+([A-Za-z0-9_\\-]{{4,25}})/i);
                                        if (m) return m[1];
                                        const t = text.trim();
                                        if (/^[A-Za-z0-9_\\-]{{4,25}}$/.test(t) && !/lay|ma|click|link|buoc|cho|wait|giay|second|loading|keo/i.test(t)) {{
                                            return t;
                                        }}
                                    }}
                                    // 2. Check element container
                                    const el = document.getElementById('{traffic_key}');
                                    if (el) {{
                                        if (el.dataset.code && /^[A-Za-z0-9_\\-]{{4,25}}$/.test(el.dataset.code)) return el.dataset.code;
                                        const d = el.getElementsByTagName('div')[0];
                                        if (d && d.innerText) {{
                                            const m = d.innerText.match(/(?:M[ãa]\\s*KM|Code|M[ãa])[\\s\\:\\-]+([A-Za-z0-9_\\-]{{4,25}})/i);
                                            if (m) return m[1];
                                        }}
                                    }}
                                    // 3. Check completed or token button
                                    const cBtn = document.querySelector('.completed, [class*="completed"], #ma-km, .ma-km, #token, [data-code]');
                                    if (cBtn) {{
                                        const val = cBtn.dataset.code || cBtn.innerText || cBtn.value || '';
                                        const m = val.match(/(?:M[ãa]\\s*KM|Code|M[ãa])[\\s\\:\\-]+([A-Za-z0-9_\\-]{{4,25}})/i);
                                        if (m) return m[1];
                                        const t = val.trim();
                                        if (/^[A-Za-z0-9_\\-]{{4,25}}$/.test(t) && !/lay|ma|click|link|buoc|cho|wait|giay/i.test(t)) return t;
                                    }}
                                    return null;
                                }}""")
                                if dom_t:
                                    cleaned = clean_code_str(dom_t)
                                    if is_valid_sponsor_code(cleaned):
                                        code_found = cleaned
                                        log(f"🎉 EXTRACTED SPONSOR CODE FROM DOM IN STEP {step}: {code_found}")
                                        break
                            except Exception:
                                pass
                    break

            if code_found:
                break

        if code_found:
            break

    if not code_found:
        time.sleep(1.5)
        dom_val = page.evaluate(f"""() => {{
            const elDirect = document.getElementById('{traffic_key}');
            if (elDirect) {{
                const t = (elDirect.dataset.code || elDirect.value || elDirect.innerText || '').trim();
                if (/^[A-Za-z0-9_\\-]{{4,20}}$/.test(t) && !/lay|ma|click|link|buoc/i.test(t)) return t;
            }}
            const selList = [
                "[id='{traffic_key}']",
                "[id='{traffic_key}'] button",
                "[id='{traffic_key}'] span",
                "[id='{traffic_key}'] div",
                '.whatoncode',
                '.ma-xac-nhan',
                '#ma-km',
                '#token',
                '[data-code]'
            ];
            for (const s of selList) {{
                try {{
                    const el = document.querySelector(s);
                    if (el) {{
                        let t = (el.dataset.code || el.value || el.innerText || '').trim();
                        const m = t.match(/(?:M[ãa]\\s*KM|M[ãa]\\s*x[áa]c\\s*nh[ậa]n|Code|M[ãa])[\\s\\:\\-]+([A-Za-z0-9]{{4,20}})/i);
                        if (m) return m[1];
                        t = t.replace(/^(?:M[ãa]\\s*KM|M[ãa]\\s*x[áa]c\\s*nh[ậa]n|Code|M[ãa])[\\s\\:\\-]+/i, '').trim();
                        if (/^[A-Za-z0-9_\\-]{{4,20}}$/.test(t) && !/lay|ma|click|link|buoc/i.test(t)) return t;
                    }}
                }} catch (e) {{}}
            }}
            return null;
        }}""")
        if dom_val and is_valid_sponsor_code(dom_val):
            code_found = clean_code_str(dom_val)
            log(f"🎉 EXTRACTED SPONSOR CODE FROM DOM: {code_found}")

    if not code_found:
        try:
            fallback_res = page.evaluate("""async () => {
                for (let k in localStorage) {
                    if (k.includes('quest')) {
                        try {
                            const q = JSON.parse(localStorage.getItem(k));
                            if (q && q.id) {
                                const endpoints = ['/widget/get_quest_code.html?id=' + q.id, 'https://s1.what-on.com/widget/get_quest_code.html?id=' + q.id];
                                for (const ep of endpoints) {
                                    try {
                                        const r = await fetch(ep, { credentials: 'include' });
                                        if (r.ok) {
                                            const res = await r.json();
                                            if (res && (res.html || res.code)) return res.html || res.code;
                                        }
                                    } catch (err) {}
                                }
                            }
                        } catch (e) {}
                    }
                }
                return null;
            }""")
            if fallback_res:
                cl = clean_code_str(fallback_res)
                if is_valid_sponsor_code(cl):
                    code_found = cl
                    log(f"🎉 EXTRACTED SPONSOR CODE VIA DIRECT FALLBACK FETCH: {code_found}")
        except Exception:
            pass

    if not code_found:
        body = page.evaluate("() => document.body.innerText")
        m = re.search(r'(?:M[ãa]\s*KM|M[ãa]\s*x[áa]c\s*nh[ậa]n|Code|M[ãa])[\s\:\-]+([A-Za-z0-9]{4,15})', body)
        if m and is_valid_sponsor_code(m.group(1)):
            code_found = clean_code_str(m.group(1))
            log(f"[+] FOUND CODE IN BODY: {code_found}")

    brain = get_brain()
    elapsed_single = round(time.time() - t_single_start, 2)
    if code_found:
        strat = "api" if code_from_api else "dom"
        brain.learn_success(sponsor_url, traffic_key, code_found, elapsed_single, winning_strategy=strat)
        brain.data_controller.mark_stage("sponsor_success", {
            "active_sponsor": sponsor_url,
            "traffic_key": traffic_key,
            "code": code_found
        })
    else:
        brain.learn_failure(sponsor_url, "code_not_found")
        brain.flow_director.handle_stage_failure("code_harvest", {"domain": sponsor_url, "error": "code_not_found"})
    return code_found

def solve_sponsor_quest(context, sponsor_url_or_list) -> str:
    urls = [sponsor_url_or_list] if isinstance(sponsor_url_or_list, str) else sponsor_url_or_list
    for idx, sponsor_url in enumerate(urls):
        if not sponsor_url:
            continue
        log(f"\n[*] [{idx+1}/{len(urls)}] Đang thử nghiệm trang tài trợ: {sponsor_url}")
        code = _solve_single_sponsor(context, sponsor_url)
        if code:
            return code
        log(f"[-] Trang {sponsor_url} không tìm thấy mã nhiệm vụ, tự động chuyển sang ứng viên tiếp theo...")
    return None
