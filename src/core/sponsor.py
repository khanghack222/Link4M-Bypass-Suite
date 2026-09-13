import re
import time
import urllib.request
import ssl
from rapidocr_onnxruntime import RapidOCR
from config import log

_OCR_INSTANCE = None
def get_ocr():
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        _OCR_INSTANCE = RapidOCR()
    return _OCR_INSTANCE

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

    return list(dict.fromkeys(results))

VALID_TLDS = [
    'com.vn', 'com.tw', 'co.uk', 'co.jp', 'com', 'net', 'org', 'io', 'cc',
    'me', 'vn', 'tw', 'vip', 'tv', 'co', 'site', 'top', 'online', 'xyz',
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

    # Expand texts with OCR typo corrections (e.g. .i0 -> .io, .c0m -> .com, .0rg -> .org)
    texts = []
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

    # Priority 0: Unmask any masked domains like shin-shih.co***.tw
    for text in texts:
        if '*' in text:
            for u in unmask_domain_candidates(text):
                if 'link4m' not in u and u not in candidates:
                    candidates.append(u)

    # Priority 1: Match URLs starting with http:// or https://
    for text in texts:
        for m in re.findall(r'https?:\/\/([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)', text):
            d = m.lower().rstrip('/')
            if 'link4m' not in d and d not in candidates:
                candidates.append(d)

    # Priority 2: Match strictly valid TLDs with word boundary (?![a-zA-Z0-9])
    for text in texts:
        for m in re.finditer(rf'([a-zA-Z0-9\-]{{2,}})\.({TLD_REGEX})(?![a-zA-Z0-9])', text, re.IGNORECASE):
            full_d = f"{m.group(1).lower()}.{m.group(2).lower()}"
            if 'link4m' not in full_d and len(full_d) >= 4 and full_d not in candidates:
                candidates.append(full_d)

    # Priority 3: Match any token with dot domain (letters/digits + dot + 2..10 letter TLD)
    for text in texts:
        cleaned = re.sub(r'[^a-zA-Z0-9\.\-\/]', ' ', text)
        for part in cleaned.split():
            part = part.strip('./-')
            m = re.search(rf'(?:[a-zA-Z0-9\-]+\.)+({TLD_REGEX})$', part, re.IGNORECASE)
            if m:
                d = part.lower().rstrip('/')
                if 'link4m' not in d and len(d) >= 4 and d not in candidates:
                    candidates.append(d)

    # Phân hạng candidate: ưu tiên domain dài hơn, có từ khóa nhà cái
    def rank_c(c):
        score = 0
        clow = c.lower()
        if any(kw in clow for kw in ['88', 'bet', 'keo', 'cai', 'casino', 'game', 'club', 'slot', 'win']):
            score += 30
        prefix = clow.split('.')[0]
        if prefix.isdigit() and len(prefix) <= 4:
            score -= 20
        score += len(clow)
        return score

    candidates.sort(key=rank_c, reverse=True)
    return candidates

def probe_domain_live(domain: str) -> str:
    for proto in ['https://', 'http://']:
        target_url = proto + domain
        try:
            req = urllib.request.Request(
                target_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=3.5) as resp:
                code = resp.getcode()
                if code in (200, 301, 302):
                    return target_url
        except Exception:
            pass
    return ""

def detect_sponsor_domain(page_link):
    all_texts = []

    # Step 1: Extract from Link4M page DOM text directly
    try:
        page_text = page_link.locator("body").inner_text()
        all_texts.extend(page_text.splitlines())
    except Exception:
        pass

    # Step 2: Extract from target sponsor image
    target_img = None
    for _ in range(6):
        for img in page_link.locator("img").all():
            src = img.get_attribute("src") or ""
            if "img.link4m.net" in src and ("/1_" in src or "advertiser" in src):
                target_img = img
                break
        if target_img:
            break
        time.sleep(0.8)

    if target_img:
        src = target_img.get_attribute("src") or ""
        log(f"[*] Found sponsor SERP image: {src}")

        img_bytes = None
        try:
            img_bytes = target_img.screenshot()
        except Exception:
            pass
        if not img_bytes:
            try:
                resp = page_link.request.get(src)
                if resp.ok:
                    img_bytes = resp.body()
            except Exception:
                pass

        if img_bytes:
            res, _ = get_ocr()(img_bytes)
            if res:
                all_texts.extend([line[1].strip() for line in res if len(line) > 1])

    candidates = extract_domain_candidates(all_texts)
    log(f"[*] Extracted domain candidates (including unmasked): {candidates}")

    # Sắp xếp và phân hạng các ứng viên:
    def rank_candidate(c):
        score = 0
        clow = c.lower()
        if any(kw in clow for kw in ['88', 'bet', 'keo', 'cai', 'casino', 'game', 'club', 'slot', 'win']):
            score += 20
        if clow.count('.') >= 2:
            score += 10
        prefix = clow.split('.')[0]
        if len(prefix) <= 3 and not prefix.isdigit():
            score -= 15
        score += len(clow) * 0.1
        return score

    candidates.sort(key=rank_candidate, reverse=True)

    # Probe live domain theo thứ tự ưu tiên
    live_urls = []
    for c in candidates:
        live_url = probe_domain_live(c)
        if live_url and live_url not in live_urls:
            live_urls.append(live_url)

    if live_urls:
        log(f"[+] Verified live sponsor website candidates: {live_urls}")
        return live_urls

    if candidates:
        fallbacks = [f"https://{c}" for c in candidates]
        log(f"[+] Fallback to candidate list: {fallbacks}")
        return fallbacks

    return []

def _solve_single_sponsor(context, sponsor_url: str) -> str:
    log(f"[*] Opening sponsor site via Google referrer: {sponsor_url}")
    page = context.new_page()

    page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

    try:
        page.goto(sponsor_url, wait_until="domcontentloaded", referer="https://www.google.com/", timeout=40000)
    except Exception as e:
        log(f"[!] Sponsor goto note: {e}")
        try: page.close()
        except Exception: pass
        return None
    time.sleep(1.5)

    html = page.content()
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
        return clean.strip()

    def is_valid_sponsor_code(text: str) -> bool:
        t = clean_code_str(text)
        if not t or len(t) < 4 or len(t) > 20:
            return False
        if any(w in t.lower() for w in ['click', 'vui lòng', 'vui long', 'link', 'bước', 'buoc', 'lay ma', 'lấy mã', 'chờ', 'cho', 'seconds', 'giây', 'vui']):
            return False
        return bool(re.match(r'^[A-Za-z0-9_\-]{4,20}$', t))

    code_found = None
    def on_resp(res):
        nonlocal code_found
        if any(ep in res.url for ep in ["get_quest_code.html", "get_code", "ajax_code", "lay_ma"]):
            try:
                data = res.json()
                raw = data.get("html") or data.get("code") or data.get("data")
                if raw:
                    val = clean_code_str(raw)
                    if is_valid_sponsor_code(val):
                        code_found = val
                        log(f"🎉 EXTRACTED SPONSOR CODE FROM API: {code_found}")
                    else:
                        log(f"[*] API intermediate message: {val}")
            except Exception:
                pass
    page.on("response", on_resp)

    btn_sel = f"[id='{traffic_key}'] button, [id='{traffic_key}'] a, [id='{traffic_key}'], button:has-text('LẤY MÃ'), button:has-text('LAY MA'), a:has-text('LẤY MÃ'), .whatoncode" if traffic_key else "button:has-text('LẤY MÃ'), button:has-text('LAY MA'), a:has-text('LẤY MÃ'), .whatoncode"

    def prep():
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
        }}""")

    visited = {sponsor_url.rstrip("/")}
    for step in range(1, 4):
        if code_found:
            break
        log(f"\n[*] EXECUTING STEP {step} ON SPONSOR SITE")

        if step > 1:
            article = None
            try:
                article_candidates = page.evaluate("""(sp_url) => {
                    const links = [];
                    const origin = new URL(sp_url).origin;
                    document.querySelectorAll('a[href]').forEach(a => {
                        try {
                            const u = new URL(a.href, window.location.href);
                            if (u.origin === origin && u.pathname.length > 2 && !u.pathname.includes('wp-admin') && !u.pathname.includes('feed') && !u.href.includes('#')) {
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
            if not article:
                article = f"{sponsor_url}/bai-viet-{step}/"
                visited.add(article.rstrip("/"))
            log(f"[*] Navigating to Step {step} article: {article}")
            try:
                page.goto(article, wait_until="domcontentloaded", timeout=35000)
            except Exception:
                pass
            time.sleep(1.5)

        prep()
        time.sleep(1.2)

        btn = page.locator(btn_sel).first
        if btn.count() == 0:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.2)
            btn = page.locator(btn_sel).first

        if btn.count() == 0:
            log(f"[!] Step {step}: Button not found, skipping...")
            # Nếu ngay ở Step 1 mà không có traffic_key và không thấy nút -> không phải trang tài trợ thật
            if step == 1 and not traffic_key:
                log(f"[!] Bước 1 không có traffic_key và nút nhiệm vụ, dừng trang này để thử ứng viên khác.")
                try: page.close()
                except Exception: pass
                return None
            continue

        log(f"[+] Step {step}: Button located. Clicking...")
        try:
            btn.click(force=True)
        except Exception:
            btn.evaluate("el => el.click()")
        time.sleep(1.5)

        sec_dur = page.evaluate(f"() => {{ const el = document.getElementById('{traffic_key}'); return el && el.dataset.time ? parseFloat(el.dataset.time) : 60; }}")
        log(f"[*] Step {step}: Countdown duration = {sec_dur}s")

        dir_wheel = 1
        for sec in range(1, int(sec_dur) + 25):
            time.sleep(1)
            dir_wheel = -dir_wheel if sec % 5 == 0 else dir_wheel
            page.mouse.wheel(0, 120 * dir_wheel)

            rem = page.evaluate(f"() => {{ const el = document.getElementById('{traffic_key}'); return el && el.dataset.time ? parseFloat(el.dataset.time) : null; }}")
            if sec % 5 == 0 or (rem is not None and rem <= 5):
                log(f"  [Step {step} - {sec}s] Remaining: {rem}s")

            if code_found or (rem is not None and rem <= 0):
                time.sleep(1.5)
                break

    if not code_found:
        time.sleep(1.5)
        dom_val = page.evaluate(f"""() => {{
            const selList = [
                '#{traffic_key}',
                '#{traffic_key} button',
                '#{traffic_key} span',
                '.whatoncode',
                '.ma-xac-nhan',
                '#ma-km',
                '#token',
                '[data-code]'
            ];
            for (const s of selList) {{
                const el = document.querySelector(s);
                if (el) {{
                    const t = (el.dataset.code || el.value || el.innerText || '').trim();
                    if (/^[A-Za-z0-9_\\-]{{4,20}}$/.test(t) && !/lay|ma|click|link|buoc/i.test(t)) return t;
                }}
            }}
            return null;
        }}""")
        if dom_val and is_valid_sponsor_code(dom_val):
            code_found = clean_code_str(dom_val)
            log(f"🎉 EXTRACTED SPONSOR CODE FROM DOM: {code_found}")

    if not code_found:
        body = page.evaluate("() => document.body.innerText")
        m = re.search(r'(?:M[ãa]\s*KM|M[ãa]\s*x[áa]c\s*nh[ậa]n|Code|M[ãa])[\s\:\-]+([A-Za-z0-9]{4,15})', body)
        if m and is_valid_sponsor_code(m.group(1)):
            code_found = clean_code_str(m.group(1))
            log(f"[+] FOUND CODE IN BODY: {code_found}")

    try:
        page.close()
    except Exception:
        pass

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
