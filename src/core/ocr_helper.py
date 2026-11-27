import sys, json, re, urllib.request, ssl, socket, concurrent.futures
sys.stdout.reconfigure(encoding='utf-8')

_rapid_engine = None
_dddd_engine = None

def get_dddd():
    global _dddd_engine
    if _dddd_engine is None:
        try:
            import ddddocr
            _dddd_engine = ddddocr.DdddOcr(show_ad=False)
        except Exception:
            _dddd_engine = False
    return _dddd_engine if _dddd_engine is not False else None

def get_engine():
    global _rapid_engine
    if _rapid_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_engine = RapidOCR()
        except Exception:
            _rapid_engine = False
    return _rapid_engine if _rapid_engine is not False else None

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

IGNORE = {
    'google.com', 'google.com.vn', 'shopee.vn', 'youtube.com', 'facebook.com',
    'tiktok.com', 'instagram.com', 'twitter.com', 'x.com', 'wikipedia.org',
    'scholar.google.com', 't.me', 'telegram.org', 'linkhuongdan.online', 'octolink.vip',
    'play.google.com', 'mudeo.app', 'apps.apple.com'
}
JUNK_TLD = ('.app', '.play')
GOOD_TLD = ('.cc', '.me', '.my', '.vip', '.tv', '.tips', '.net', '.live', '.com', '.games', '.in', '.online')

_DNS_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)

def _dns_check(domain: str, timeout: float = 2.0) -> bool:
    """Kiểm tra phân giải DNS có giới hạn thời gian (2s) để tránh treo tiến trình."""
    try:
        future = _DNS_POOL.submit(socket.gethostbyname, domain)
        future.result(timeout=timeout)
        return True
    except Exception:
        return False

def has_traffic_widget(d):
    if not _dns_check(d, timeout=2.0):
        return False

    try:
        req = urllib.request.Request(
            f'https://{d}/',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.google.com/'
            }
        )
        with urllib.request.urlopen(req, context=ctx, timeout=4.0) as resp:
            html = resp.read(1024 * 1024).decode('utf-8', errors='ignore').lower()
        if 'trafficqq.io.vn' in html:
            return False
        return any(k in html for k in ['shortearn', 'octolink', 'trafficvip.vip', 'click90s', '4mmo', 'trafficvn', 'check/job'])
    except:
        return False

def resolve_domain(img_url):
    try:
        req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://linkhuongdan.online/'})
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            data = resp.read(5 * 1024 * 1024)
    except Exception as e:
        return []

    candidates = []

    # Priority 1: Ultra-fast ddddocr pass (~10ms, 10MB RAM)
    dddd = get_dddd()
    if dddd and data:
        try:
            d_text = dddd.classification(data)
            for p in (d_text or "").split():
                p = p.strip('()[]{}<>,;:\'\"')
                m = re.search(r'(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', p)
                if m:
                    d = m.group(1).lower()
                    if d not in IGNORE and not any(d.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp'] + list(JUNK_TLD)):
                        if d not in candidates:
                            candidates.append(d)
        except Exception:
            pass

    # Priority 2: RapidOCR multi-line pass if no candidate or fallback needed
    if not candidates:
        engine = get_engine()
        if engine and data:
            try:
                lines, _ = engine(data)
                if lines:
                    for l in lines:
                        text = l[1].strip()
                        for p in text.split():
                            p = p.strip('()[]{}<>,;:\'\"')
                            m = re.search(r'(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', p)
                            if m:
                                d = m.group(1).lower()
                                if d in IGNORE or any(d.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp'] + list(JUNK_TLD)):
                                    continue
                                if d not in candidates:
                                    candidates.append(d)
            except Exception:
                pass

    # Priority 3: WebAI-to-API Gemini Vision if dddd & RapidOCR found nothing
    if not candidates and data:
        try:
            try:
                from webai_client import is_webai_available, ocr_image_webai
            except ImportError:
                from src.core.webai_client import is_webai_available, ocr_image_webai

            if is_webai_available():
                w_text = ocr_image_webai(data, prompt="Extract all website domains or URLs mentioned in this image. Return as a space-separated list.")
                for p in (w_text or "").split():
                    p = p.strip('()[]{}<>,;:\'\"')
                    m = re.search(r'(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)', p)
                    if m:
                        d = m.group(1).lower()
                        if d not in IGNORE and not any(d.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp'] + list(JUNK_TLD)):
                            if d not in candidates:
                                candidates.append(d)
        except Exception:
            pass

    ranked = [d for d in candidates if d.endswith(GOOD_TLD)] + [d for d in candidates if not d.endswith(GOOD_TLD)]
    verified = []
    if ranked:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(ranked))) as executor:
            future_to_d = {executor.submit(has_traffic_widget, d): d for d in ranked[:10]}
            for future in concurrent.futures.as_completed(future_to_d):
                d = future_to_d[future]
                try:
                    if future.result():
                        verified.append(d)
                except:
                    pass

    if verified:
        verified.sort(key=lambda d: 0 if d.endswith(GOOD_TLD) else 1)
        return verified
    return [d for d in ranked if not d.endswith('.com') and not d.endswith('.app')] or ranked[:1]

if __name__ == '__main__':
    url = sys.argv[1]
    res = resolve_domain(url)
    print(json.dumps(res))

