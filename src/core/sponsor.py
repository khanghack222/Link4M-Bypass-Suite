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

def extract_domain_candidates(texts):
    candidates = []

    # Priority 0: Unmask any masked domains like shin-shih.co***.tw
    for text in texts:
        if '*' in text:
            for u in unmask_domain_candidates(text):
                if 'link4m' not in u and u not in candidates:
                    candidates.append(u)

    # Priority 1: Match full URLs http:// or https://
    for text in texts:
        for m in re.findall(r'https?:\/\/([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)', text):
            d = m.lower().rstrip('/')
            if 'link4m' not in d and d not in candidates:
                candidates.append(d)

    # Priority 2: Generic domain pattern (any 2-10 letter TLD)
    for text in texts:
        cleaned = re.sub(r'[^a-zA-Z0-9\.\-\/]', ' ', text)
        for part in cleaned.split():
            part = part.strip('./-')
            m = re.search(r'(?:[a-zA-Z0-9\-]+\.)+([a-zA-Z]{2,10})$', part)
            if m:
                tld = m.group(1).lower()
                if tld in MEDIA_EXTS:
                    continue
                d = part.lower().rstrip('/')
                if 'link4m' not in d and len(d) >= 4 and d not in candidates:
                    candidates.append(d)

    return candidates

def probe_domain_live(domain: str) -> str:
    for proto in ['https://', 'http://']:
        target_url = proto + domain
        try:
            req = urllib.request.Request(
                target_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=4.0) as resp:
                code = resp.getcode()
                if code in (200, 301, 302):
                    return target_url
        except Exception:
            pass
    return ""

def detect_sponsor_domain(page_link) -> str:
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

    # Probe live domain
    for c in candidates:
        live_url = probe_domain_live(c)
        if live_url:
            log(f"[+] Verified live sponsor website: {live_url}")
            return live_url

    if candidates:
        fallback = f"https://{candidates[0]}"
        log(f"[+] Fallback to top candidate: {fallback}")
        return fallback

    return ""

def solve_sponsor_quest(context, sponsor_url: str) -> str:
    log(f"[*] Opening sponsor site via Google referrer: {sponsor_url}")
    page = context.new_page()

    page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

    try:
        page.goto(sponsor_url, wait_until="domcontentloaded", referer="https://www.google.com/", timeout=40000)
    except Exception as e:
        log(f"[!] Sponsor goto note: {e}")
    time.sleep(1.5)

    html = page.content()
    m_key = re.search(r'(?:what-on\.com|website-analytics\.net|traffic)[^"\']*?key=([a-zA-Z0-9]+)', html)
    traffic_key = m_key.group(1) if m_key else None
    if not traffic_key:
        div_ids = page.evaluate("() => Array.from(document.querySelectorAll('div[id]')).map(d => d.id).filter(id => /^[a-zA-Z0-9]{8}$/.test(id))")
        if div_ids:
            traffic_key = div_ids[0]
    log(f"[*] Detected traffic_key: {traffic_key}")

    code_found = None
    def on_resp(res):
        nonlocal code_found
        if "get_quest_code.html" in res.url:
            try:
                data = res.json()
                if data.get("success") and data.get("html"):
                    code_found = data.get("html")
                    log(f"🎉 EXTRACTED SPONSOR CODE FROM API: {code_found}")
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
                for a in page.locator("a[href^='https://']").all():
                    h = (a.get_attribute("href") or "").rstrip("/")
                    if sponsor_url in h and h not in visited and not any(x in h for x in [".jpg", ".png", ".webp", ".css", ".js", "feed", "wp-", "#"]):
                        article = h
                        visited.add(h)
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
        body = page.evaluate("() => document.body.innerText")
        m = re.search(r'(?:M[ãa]\s*KM|M[ãa]\s*x[áa]c\s*nh[ậa]n|Code)[\s\:\-]+([A-Za-z0-9]{4,8})', body)
        if m:
            code_found = m.group(1)
            log(f"[+] FOUND CODE IN BODY: {code_found}")

    try:
        page.close()
    except Exception:
        pass

    return code_found
