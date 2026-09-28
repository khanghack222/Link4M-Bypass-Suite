import os
import json
import re
import time
import urllib.request
import ssl
import base64
import requests
from config import log
try:
    from brain import get_brain
except ImportError:
    from src.core.brain import get_brain

_OCR_INSTANCE = None
_DDDD_INSTANCE = None

def get_dddd():
    global _DDDD_INSTANCE
    if _DDDD_INSTANCE is None:
        try:
            import ddddocr
            _DDDD_INSTANCE = ddddocr.DdddOcr(show_ad=False)
        except Exception:
            _DDDD_INSTANCE = False
    return _DDDD_INSTANCE if _DDDD_INSTANCE is not False else None

def get_ocr():
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_INSTANCE = RapidOCR()
        except Exception as e:
            log(f"[!] RapidOCR init note: {e}")
            _OCR_INSTANCE = False
    return _OCR_INSTANCE if _OCR_INSTANCE is not False else None

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

def extract_domain_candidates(ocr_lines, quest_info=None):
    candidates = []
    raw_texts = []

    # Priority -1: Direct domain hint from quest instructions if already a valid domain
    if quest_info and quest_info.get("domain_hint"):
        dh = quest_info["domain_hint"].replace("www.", "").strip('./- ')
        if '.' in dh and not any(c in dh for c in ['*', '★']) and len(dh) >= 4:
            if 'link4m' not in dh and 'google' not in dh:
                candidates.append(dh)

    for item in (ocr_lines or []):
        if isinstance(item, str):
            t = item.strip()
            if t:
                raw_texts.append(t)
        elif isinstance(item, (list, tuple)) and len(item) > 1:
            t = str(item[1]).strip()
            if t:
                raw_texts.append(t)

    # Extract candidate TLDs for domain unmasking or regex
    detected_tlds = []
    for txt in raw_texts:
        for tld in VALID_TLDS:
            if tld in txt.lower() and tld not in detected_tlds:
                detected_tlds.append(tld)

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

    # Extract potential domain patterns like KEOBONGDA11 NET or keobongda11 . net
    for t in list(texts):
        for tld in VALID_TLDS:
            m_sep = re.findall(rf'([a-zA-Z0-9\-]{{3,}})\s*(?:dot|\.)?\s*({tld})\b', t, re.IGNORECASE)
            for stem, ext in m_sep:
                comb = f"{stem.lower()}.{ext.lower()}"
                if 'link4m' not in comb and 'google' not in comb and comb not in candidates:
                    candidates.append(comb)

    # Check consecutive lines (e.g. line i: "KEOBONGDA" or "KEOBONGDA11", line i+1: "NET")
    for idx_l in range(len(raw_texts) - 1):
        l1 = re.sub(r'[^a-zA-Z0-9\-]', '', raw_texts[idx_l]).lower()
        l2 = re.sub(r'[^a-zA-Z0-9\-]', '', raw_texts[idx_l + 1]).lower()
        if l2 in VALID_TLDS and len(l1) >= 3:
            comb = f"{l1}.{l2}"
            if 'link4m' not in comb and 'google' not in comb and comb not in candidates:
                candidates.append(comb)
            # Also generate common betting/sports brand number variations (e.g. keobongda -> keobongda11, keobongda88)
            if any(k in l1 for k in ['keo', 'bong', 'bet', 'soi', 'cai']):
                c_stem = re.sub(r'\d+$', '', l1)
                for num_suf in ['11', '88', '24h', 'net', 'onl', '247']:
                    c_cand = f"{c_stem}{num_suf}.{l2}"
                    if c_cand not in candidates: candidates.append(c_cand)
            elif any(l1.endswith(d) for d in ['11', '1', '2', '3', '88']):
                c_stem = re.sub(r'\d+$', '', l1)
                for num_suf in ['11', '88', '']:
                    c_cand = f"{c_stem}{num_suf}.{l2}"
                    if c_cand not in candidates: candidates.append(c_cand)

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

    EXCLUDED_DOMAINS = {'gmail.com', 'gmal.com', 'gmaii.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'mail.com', 'link4m.net', 'link4m.com', 'link4m.org', 'link4m.co', 'link4m.me', 'us.org', 'uk.com', 'us.com', 'vn.com'}
    SEARCH_ARTIFACTS = ['google', 'googie', 'g00gle', 'link4m', 'iink4m', 'chrome', 'youtube', 'facebook', 'tiktok', 'instagram', 'twitter', 'wikipedia', 'shopee', 'lazada', 'truycap']
    
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

    candidates = [
        c for c in candidates 
        if not any(art in c.lower() for art in SEARCH_ARTIFACTS) 
        and c.lower() not in EXCLUDED_DOMAINS 
        and len(c.split('.')[0]) >= 3
    ]
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
                html = resp.read(500000).decode('utf-8', errors='ignore')
                has_script = any(k in html.lower() for k in ['website-analytics', 'service-v', 'what-on.com', 'traffic-button', 'traffic.com.vn', 'whatoncode', 'lấy mã', 'lay ma'])
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

def extract_quest_instructions(all_texts: list) -> dict:
    """
    Trích xuất chính xác cấu trúc nhiệm vụ từ Link4M:
    - Bước 2: Từ khóa tìm kiếm (search keyword).
    - Bước 3: Domain đích hoặc Domain Mask (target domain hint).
    - Trang: Vị trí trang tìm kiếm (page hint, mặc định 1).
    """
    clean_lines = [l.strip() for l in all_texts if l and isinstance(l, str) and l.strip()]
    
    keyword = ""
    domain_hint = ""
    page_hint = 1
    
    # 1. Quét tìm Bước 2 (Từ khóa)
    idx_s2 = -1
    for i, l in enumerate(clean_lines):
        if re.search(r'(?:b[uư][oơ]c|buroc)\s*2', l, re.IGNORECASE):
            idx_s2 = i
            break
            
    if idx_s2 != -1:
        line_s2 = clean_lines[idx_s2]
        cand = re.sub(r'^(?:b[uư][oơ]c|buroc)\s*2\s*[:\.]?\s*', '', line_s2, flags=re.IGNORECASE)
        cand = re.sub(r'^(?:g[oõ]|go)?\s*(?:t[iì]m|tim)?\s*(?:t[uừ]|tir|tu)?\s*(?:kh[oó]a|khoa)?[:\.\s]*', '', cand, flags=re.IGNORECASE).strip()
        if len(cand) >= 2 and not any(k in cand.lower() for k in ['google', 'bước', 'buroc']):
            keyword = cand
        elif idx_s2 + 1 < len(clean_lines):
            next_l = clean_lines[idx_s2 + 1]
            if not re.search(r'(?:b[uư][oơ]c|buroc|google)', next_l, re.IGNORECASE):
                keyword = next_l.strip()

    if not keyword:
        # Fallback: Quét ô tìm kiếm "Google <keyword> Q"
        for i, l in enumerate(clean_lines):
            if l.strip().lower() == "google" and i + 1 < len(clean_lines):
                if clean_lines[i+1].lower() != "q" and not re.search(r'(?:b[uư][oơ]c|buroc)', clean_lines[i+1], re.IGNORECASE):
                    keyword = clean_lines[i+1].strip()
                    break

    # 2. Quét tìm Bước 3 (Domain đích & Số trang)
    idx_s3 = -1
    for i, l in enumerate(clean_lines):
        if re.search(r'(?:b[uư][oơ]c|buroc)\s*3', l, re.IGNORECASE):
            idx_s3 = i
            break
            
    if idx_s3 != -1:
        s3_tokens = []
        l_s3 = re.sub(r'^(?:b[uư][oơ]c|buroc)\s*3\s*[:\.]?\s*', '', clean_lines[idx_s3], flags=re.IGNORECASE)
        l_s3 = re.sub(r'^(?:b[aá]m|click|v[aà]o|t[iì]m)?\s*(?:website|trang\s*web|web|site)?[:\.\s]*', '', l_s3, flags=re.IGNORECASE).strip()
        if l_s3: s3_tokens.append(l_s3)
        for j in range(idx_s3 + 1, min(idx_s3 + 5, len(clean_lines))):
            if re.search(r'(?:b[uư][oơ]c|buroc)\s*4', clean_lines[j], re.IGNORECASE):
                break
            s3_tokens.append(clean_lines[j])
            
        combined_s3 = " ".join(s3_tokens)
        p_m = re.search(r'(?:[oơ]\s*trang|trang)\s*(\d+)', combined_s3, re.IGNORECASE)
        if p_m:
            page_hint = int(p_m.group(1))
            combined_s3 = combined_s3[:p_m.start()] + " " + combined_s3[p_m.end():]
            
        combined_s3 = re.sub(r'\s*\.\s*', '.', combined_s3)
        for token in combined_s3.split():
            clean_tok = token.strip('./- ')
            if '.' in clean_tok or any(c in clean_tok for c in ['*', '★']):
                if not any(k in clean_tok.lower() for k in ['google', 'link4m']):
                    domain_hint = clean_tok.lower()
                    break

    return {
        "keyword": keyword,
        "domain_hint": domain_hint,
        "page_hint": page_hint
    }

_env_key = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_KEY = _env_key if (_env_key and not _env_key.startswith("sk-")) else ""
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

def resolve_domain_gemini_ai(keyword: str, domain_hint: str = "") -> list:
    """
    Sử dụng Google Gemini AI Studio (Flash-Lite series) siêu tiết kiệm token và tốc độ ~1.2s
    để giải mã và suy luận chính xác website tài trợ từ từ khóa và mask.
    """
    if not keyword and not domain_hint:
        return []
    
    models_to_try = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
    prompt = f'Given Vietnamese traffic quest search keyword: "{keyword}" and target domain hint/mask: "{domain_hint}", deduce and return ONLY a JSON array of the 1 to 2 most probable exact domains (e.g. ["domain.com"]). No markdown, no extra explanation.'
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    
    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=4.0) as r:
                res = json.loads(r.read().decode("utf-8"))
                txt = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                txt = re.sub(r"^```(?:json)?", "", txt, flags=re.IGNORECASE).rstrip("`").strip()
                arr = json.loads(txt)
                if isinstance(arr, list):
                    doms = []
                    for d in arr:
                        c = str(d).replace("www.", "").strip("./- ").lower()
                        if "." in c and c not in doms:
                            doms.append(c)
                    if doms:
                        log(f"[+] [Gemini AI {m}] Suy luan chinh xac domain dich: {doms}")
                        return doms
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            log(f"[!] Gemini AI ({m}): HTTP {e.code}")
        except Exception as e:
            log(f"[!] Gemini AI ({m}): {e}")
            
    return []

_GEMINI_VISION_CACHE = {}

def analyze_quest_images_gemini_vision(image_bytes_list: list) -> dict:
    """
    Tải trực tiếp ảnh nhiệm vụ và gửi cho Gemini Flash-Lite Multimodal Vision:
    AI trực tiếp 'nhìn' hình ảnh hướng dẫn, bóc tách chính xác từ khóa Google và domain đích (kể cả bị che sao ***).
    """
    if not image_bytes_list:
        return {}
    # Check cache by MD5 hash of image bytes to save tokens
    import hashlib
    hasher = hashlib.md5(usedforsecurity=False)
    for b in image_bytes_list:
        if b: hasher.update(b[:4096])
    cache_key = hasher.hexdigest()
    if cache_key in _GEMINI_VISION_CACHE:
        log("[*] 👁️ [Gemini Cache] Tái sử dụng kết quả Vision đã phân tích (0 tokens)...")
        return _GEMINI_VISION_CACHE[cache_key]


    models_to_try = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
    parts = [{
        "text": (
            "Analyze these Vietnamese shortlink quest instructions and mission screenshots.\n"
            "CRITICAL: Look carefully at all images, especially website headers, red arrows, red boxes, logos, and branding text (e.g. \"KEOBONGDA11.NET\", \"nhandinhkeobongdaonl.com\"). Often the target website domain or logo name is highlighted by red arrows or red text.\n"
            "Extract the search instructions and return ONLY a valid JSON object with:\n"
            "- \"keyword\": The Google search query (e.g. \"keo nha cai\").\n"
            "- \"domain_hint\": The target domain or masked domain shown in text or logos (e.g. \"keobongda11.net\", \"soikeob***.live\").\n"
            "- \"target_domains\": Array of deduced exact live website domains from text, logos, or hints (e.g. [\"keobongda11.net\", \"soikeobong.live\"]).\n"
            "- \"page_hint\": Target Google search page number (integer, default 1).\n"
            "Return ONLY raw JSON, no markdown, no other text."
        )
    }]

    # Prioritize substantive images over small icons
    sorted_imgs = sorted([b for b in image_bytes_list if b and len(b) > 800], key=len, reverse=True)
    for b in sorted_imgs[:8]:
        mime = "image/png"
        if b.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        elif b.startswith(b"RIFF") and b[8:12] == b"WEBP":
            mime = "image/webp"
        parts.append({
            "inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(b).decode("utf-8")
            }
        })

    if len(parts) <= 1:
        return {}

    payload = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")

    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8.0) as r:
                res = json.loads(r.read().decode("utf-8"))
                txt = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                txt = re.sub(r"^```(?:json)?", "", txt, flags=re.IGNORECASE).rstrip("`").strip()
                data = json.loads(txt)
                if isinstance(data, dict):
                    _GEMINI_VISION_CACHE[cache_key] = data

                    log(f"[+] 👁️ [Gemini Vision {m}] Nhìn ảnh & trích xuất nhiệm vụ thành công: {data}")
                    return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            log(f"[!] Gemini Vision ({m}): HTTP {e.code}")
        except Exception as e:
            log(f"[!] Gemini Vision ({m}): {e}")

    return {}

VN_MATH_NUMS = {
    'khong': 0, 'mot': 1, 'hai': 2, 'ba': 3, 'bon': 4, 'nam': 5,
    'sau': 6, 'bay': 7, 'tam': 8, 'chin': 9, 'muoi': 10
}

def solve_math_captcha_gemini(img_b64: str, answers: list):
    """
    Giải bài toán captcha (ví dụ 'sáu - hai = ?' hoặc '8 + 5 = ?') cho các trang tài trợ Ontops/BestTraffic.
    Ưu tiên: RapidOCR cục bộ siêu tốc (0 MB RAM, 0 latency, 0 token), fallback Gemini nếu có key.
    """
    if not answers:
        return None

    # Priority 1: Giải cục bộ siêu tốc bằng OCR + Heuristics toán học (0 tokens, ~50ms)
    try:
        import numpy as np
        import cv2
        img_bytes = base64.b64decode(img_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        mask = (img[:, :, 0] < 125) & (img[:, :, 1] < 125) & (img[:, :, 2] < 125)
        clean = np.ones_like(img) * 255
        clean[mask] = [0, 0, 0]
        padded = cv2.copyMakeBorder(clean, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        resized = cv2.resize(padded, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)

        ocr_engine = get_ocr()
        if ocr_engine:
            res_ocr, _ = ocr_engine(resized)
            raw_text = ' '.join(r[1] for r in res_ocr) if res_ocr else ''
            norm = raw_text.lower()
            norm = norm.replace('ă','a').replace('â','a').replace('ơ','o').replace('ô','o').replace('ư','u').replace('đ','d')
            norm = re.sub(r'tr[iuorv]+', '-', norm)
            norm = norm.replace('cong', '+').replace('x', '*').replace('nhan', '*').replace('#', '*').replace(':', '/')

            for op in ['+', '-', '*', '/']:
                if op in norm:
                    parts = norm.split(op, 1)
                    def get_v(s):
                        clean_s = re.sub(r'[^a-z0-9]', '', s.split('=')[0])
                        if clean_s.isdigit(): return int(clean_s)
                        for k, val in VN_MATH_NUMS.items():
                            if k in clean_s: return val
                        return None
                    v1 = get_v(parts[0])
                    v2 = get_v(parts[1])
                    if v1 is not None and v2 is not None:
                        calc = None
                        if op == '+': calc = v1 + v2
                        elif op == '-': calc = v1 - v2
                        elif op == '*': calc = v1 * v2
                        elif op == '/': calc = v1 // v2 if v2 != 0 else 0
                        if calc is not None and calc in answers:
                            log(f"[+] ⚡ Giải bài toán Captcha cục bộ bằng RapidOCR: {v1} {op} {v2} = {calc} (0 token)")
                            return calc
    except Exception as e_local:
        log(f"[!] Local math OCR pass error: {e_local}")

    # Priority 2: Fallback Gemini Flash-Lite nếu có API Key hợp lệ
    try:
        parts = [
            {"text": f"Solve the math problem in this image. The choices are {answers}. Return ONLY a JSON object with key 'answer' pointing to the correct integer choice, e.g. {{\"answer\": 4}}."},
            {"inline_data": {"mime_type": "image/png", "data": img_b64}}
        ]
        payload = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            txt = data["candidates"][0]["content"]["parts"][0]["text"]
            txt_clean = re.sub(r"^```(?:json)?", "", txt.strip(), flags=re.IGNORECASE).rstrip("`").strip()
            parsed = json.loads(txt_clean)
            if "answer" in parsed:
                ans = int(parsed["answer"])
                log(f"[+] 🧠 Gemini Vision giải bài toán captcha: {ans} (từ các lựa chọn: {answers})")
                return ans
    except Exception:
        pass
    return answers[0] if answers else None

def fallback_ai_search(query: str, domain_hint: str = "", use_gemini: bool = False) -> list:
    """
    Search siêu tốc kết hợp DuckDuckGo/Bing giả lập TLS Chrome 124 (0 token, miễn phí 100%).
    Chỉ gọi Gemini khi use_gemini=True để tiết kiệm tối đa quota API.
    """
    results = []
    
    # Lớp 1: Chỉ gọi Gemini khi được yêu cầu rõ ràng (tiết kiệm token)
    if use_gemini:
        gemini_doms = resolve_domain_gemini_ai(query, domain_hint)
        for gd in gemini_doms:
            if gd not in results:
                results.append(gd)


    blacklist = ['google.', 'youtube.com', 'facebook.com', 'tiktok.com', 'zalo.me', 'instagram.com', 'twitter.com', 'x.com', 'wikipedia.org', 'link4m.']
    
    clean_stem = domain_hint.replace('www.', '').split('.')[0].replace('*', '').strip() if domain_hint else ""
    queries_to_try = []
    if clean_stem and len(clean_stem) >= 3:
        queries_to_try.append(f"{query} {clean_stem}")
    queries_to_try.append(query)
    
    try:
        from curl_cffi import requests
        from bs4 import BeautifulSoup
    except Exception:
        return results

    for q in queries_to_try:
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
            r = requests.get(url, impersonate="chrome124", timeout=5)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select("a.result__url"):
                    txt = a.get_text().strip()
                    d = txt.split('/')[0].replace('www.', '').lower().strip()
                    if '.' in d and not any(b in d for b in blacklist):
                        if d not in results:
                            results.append(d)
            if results:
                break
        except Exception:
            pass

    if clean_stem:
        results.sort(key=lambda d: 1000 if clean_stem in d else 0, reverse=True)
    return results

def search_google_ai_for_sponsor(context, quest_info: dict) -> list:
    """
    Tận dụng Google AI Search với URL tối ưu:
    https://www.google.com/search?q=&sourceid=chrome&ie=UTF-8&amc=1&udm=50&aep=42&cud=0&source=chrome.crn.rb
    Chấp cả che hay mã hóa, chỉ cần lộ từ khóa + hint là biết ngay domain đích!
    """
    keyword = quest_info.get("keyword", "").strip()
    domain_hint = quest_info.get("domain_hint", "").strip()
    page_hint = quest_info.get("page_hint", 1)

    if not keyword and not domain_hint:
        return []

    clean_stem = domain_hint.replace('www.', '').split('.')[0].replace('*', '').strip() if domain_hint else ""
    target_q = f"{keyword} {clean_stem}".strip() if clean_stem and len(clean_stem) >= 3 else keyword
    if not target_q:
        target_q = domain_hint

    log(f"[*] 🔍 AI Google Search: Đang truy vấn Google AI với từ khóa: '{target_q}' (Trang {page_hint})...")
    results = []

    # Ưu tiên trực tiếp: Nếu domain_hint đã là domain hoàn chỉnh và hợp lệ
    if domain_hint and '.' in domain_hint and not any(c in domain_hint for c in ['*', '★']):
        d_clean = domain_hint.replace('www.', '')
        if d_clean not in results:
            results.append(d_clean)

    search_page = None
    try:
        search_page = context.new_page()
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(target_q)}&sourceid=chrome&ie=UTF-8&amc=1&udm=50&aep=42&cud=0&source=chrome.crn.rb"
        if page_hint > 1:
            url += f"&start={(page_hint - 1) * 10}"

        search_page.goto(url, wait_until="domcontentloaded", timeout=12000)
        time.sleep(1.0)

        # Kiểm tra xem có bị trang sorry chặn không
        if "sorry" not in search_page.url:
            found_domains = search_page.evaluate("""() => {
                const doms = [];
                const blacklist = [
                    'google.', 'youtube.com', 'facebook.com', 'tiktok.com', 
                    'instagram.com', 'twitter.com', 'x.com', 'wikipedia.org', 
                    'pinterest.com', 'reddit.com', 'linkedin.com', 'link4m.',
                    'microsoft.com', 'apple.com', 'shopee.vn', 'lazada.vn', 'zalo.me'
                ];
                const links = document.querySelectorAll('div#search a[href], div#rso a[href], div.g a[href], a[jsname], a[data-ved]');
                links.forEach(a => {
                    const href = a.href || '';
                    try {
                        const u = new URL(href);
                        if (u.protocol.startsWith('http')) {
                            const host = u.hostname.toLowerCase().replace(/^www\\./, '');
                            if (!blacklist.some(b => host.includes(b)) && host.includes('.')) {
                                if (!doms.includes(host)) {
                                    doms.push(host);
                                }
                            }
                        }
                    } catch(e) {}
                });
                return doms;
            }""")
            if found_domains:
                log(f"[+] 🔍 Google AI Search tìm thấy {len(found_domains)} domain hữu cơ: {found_domains[:6]}")
                for fd in found_domains:
                    if fd not in results:
                        results.append(fd)
        else:
            log("[!] Google yêu cầu Captcha/Sorry. Tự động kích hoạt AI Search Engine Fallback siêu tốc...")
            fallback_doms = fallback_ai_search(target_q, domain_hint)
            if fallback_doms:
                log(f"[+] ⚡ AI Fallback Search tìm thấy domain đích: {fallback_doms[:4]}")
                for fd in fallback_doms:
                    if fd not in results:
                        results.append(fd)
    except Exception as e:
        log(f"[!] AI Google Search ghi nhận ngoại lệ: {e}. Kích hoạt Fallback Search...")
        fallback_doms = fallback_ai_search(target_q, domain_hint)
        for fd in fallback_doms:
            if fd not in results:
                results.append(fd)
    finally:
        if search_page:
            try:
                search_page.close()
            except Exception:
                pass

    if not results and keyword:
        fallback_doms = fallback_ai_search(keyword, domain_hint)
        for fd in fallback_doms:
            if fd not in results:
                results.append(fd)

    if clean_stem:
        results.sort(key=lambda d: 1000 if clean_stem in d else 0, reverse=True)

    return results

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
    imgs_info = []
    for _poll in range(16):
        try:
            curr_imgs = page_link.evaluate("""() => {
                const res = [];
                document.querySelectorAll('#advertise-html-wrapper img, .main-content img, img').forEach(img => {
                    const s = img.src || '';
                    if (s.startsWith('data:image/')) {
                        if (s.length > 50) res.push({ type: 'b64', src: s });
                    } else if (s.includes('link4m.net') || s.includes('advertiser') || /\\d+_\\d+\\.(?:jpg|png|webp)/.test(s)) {
                        res.push({ type: 'url', src: s });
                    }
                });
                return res;
            }""")
            if curr_imgs:
                imgs_info = curr_imgs
                has_adv = any(it.get('type') == 'url' and ('advertiser' in it.get('src', '') or 'link4m' in it.get('src', '')) for it in imgs_info)
                if has_adv and len(imgs_info) >= 3:
                    break
        except Exception:
            pass
        time.sleep(0.25)

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

    # Phase 1: Direct Gemini Multimodal Vision (Tải ảnh nhiệm vụ gửi trực tiếp cho AI nhìn)
    valid_imgs = [b for b in all_img_bytes if b]
    ai_vision_res = {}
    if valid_imgs:
        log(f"[*] 👁️ Gửi {len(valid_imgs)} ảnh nhiệm vụ cho Gemini Multimodal Vision phân tích trực tiếp...")
        ai_vision_res = analyze_quest_images_gemini_vision(valid_imgs)

    # Phase 1.1: Only run OCR as fallback if Gemini Vision fails
    cloud_texts = []
    if valid_imgs and not (ai_vision_res and (ai_vision_res.get("keyword") or ai_vision_res.get("domain_hint") or ai_vision_res.get("target_domains"))):
        log("[*] Gemini Vision không trích xuất đủ, kích hoạt fallback Local RapidOCR...")
        ocr_inst = get_ocr()
        for img_b in valid_imgs:
            try:
                res_ocr, _ = ocr_inst(img_b)
                if res_ocr:
                    for line in res_ocr:
                        if len(line) > 1 and line[1].strip():
                            cloud_texts.append(line[1].strip())
            except Exception:
                pass

    full_ocr_corpus = all_texts + cloud_texts
    quest_info = extract_quest_instructions(full_ocr_corpus)

    # Hòa trộn kết quả từ Gemini Vision nếu có
    if ai_vision_res:
        if ai_vision_res.get("keyword"):
            quest_info["keyword"] = ai_vision_res["keyword"]
        if ai_vision_res.get("domain_hint"):
            quest_info["domain_hint"] = ai_vision_res["domain_hint"]
        if ai_vision_res.get("page_hint"):
            quest_info["page_hint"] = ai_vision_res["page_hint"]

    if quest_info.get("keyword") or quest_info.get("domain_hint"):
        log(f"[*] 🎯 Cấu trúc nhiệm vụ: Từ khóa='{quest_info['keyword']}', Domain Hint='{quest_info['domain_hint']}', Trang={quest_info['page_hint']}")

    # Phase 1.5: Tận dụng AI Google Search trực tiếp bằng từ khóa nhiệm vụ
    google_candidates = []
    if ai_vision_res and ai_vision_res.get("target_domains"):
        for td in ai_vision_res["target_domains"]:
            clean_td = td.replace("www.", "").strip("./- ").lower()
            if "." in clean_td and clean_td not in google_candidates:
                google_candidates.append(clean_td)

    if hasattr(page_link, 'context') and (quest_info.get("keyword") or quest_info.get("domain_hint")):
        ai_search_cands = search_google_ai_for_sponsor(page_link.context, quest_info)
        for sc in ai_search_cands:
            if sc not in google_candidates:
                google_candidates.append(sc)

    candidates = extract_domain_candidates(full_ocr_corpus, quest_info=quest_info)

    # Phase 2: Automatic Fallback to Local RapidOCR if Cloud API & Google returned no candidates
    if not candidates and not google_candidates and valid_imgs:
        log("[!] Cloud OCR chưa đủ dữ liệu, tự động kích hoạt Local RapidOCR AI...")
        ocr = get_ocr()
        for idx_img, img_bytes in enumerate(valid_imgs):
            try:
                res, _ = ocr(img_bytes)
                if res:
                    for line in res:
                        if len(line) > 1:
                            all_texts.append(line[1].strip())
            except Exception:
                pass
        full_ocr_corpus = all_texts
        quest_info = extract_quest_instructions(full_ocr_corpus)
        if hasattr(page_link, 'context') and (quest_info.get("keyword") or quest_info.get("domain_hint")):
            google_candidates = search_google_ai_for_sponsor(page_link.context, quest_info)
        candidates = extract_domain_candidates(full_ocr_corpus, quest_info=quest_info)
    else:
        all_texts.extend(cloud_texts)
        log(f"[+] Cloud OCR hoàn tất siêu tốc ({len(cloud_texts)} dòng chữ trích xuất).")

    # Đưa các domain từ Google Search lên ưu tiên hàng đầu tuyệt đối
    for gd in reversed(google_candidates):
        if gd in candidates:
            candidates.remove(gd)
        candidates.insert(0, gd)

    brain = get_brain()
    candidates = brain.prioritize_candidates(candidates)

    # Sắp xếp và phân hạng các ứng viên:
    clean_stem = quest_info.get("domain_hint", "").replace("www.", "").split(".")[0].replace("*", "").strip().lower()
    vision_targets = [td.replace("www.", "").strip("./- ").lower() for td in (ai_vision_res.get("target_domains") or []) if "." in td]
    def rank_candidate(c):
        score = 0
        clow = c.lower()
        for vt in vision_targets:
            if vt == clow or vt in clow:
                score += 50000
        if clean_stem and len(clean_stem) >= 3 and clean_stem in clow:
            score += 5000
        if clow in google_candidates:
            score += 3000
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
    log(f"[*] Trích xuất {len(candidates)} tên miền ứng viên (sau khi ưu tiên Google Search & Brain): {candidates}")

    log(f"[*] Đang kiểm tra kết nối & DNS live probe cho các ứng viên...")
    # Probe live domain: Giữ nguyên thứ tự ưu tiên tuyệt đối từ AI Vision / Domain Hint!
    vision_live_urls = []
    stem_live_urls = []
    script_urls = []
    other_live_urls = []

    for c in candidates[:12]:
        live_url, has_sc = probe_domain_live(c)
        if live_url:
            clow = c.lower()
            is_exact_vision = any(vt == clow or vt in clow for vt in vision_targets)
            is_stem = bool(clean_stem and len(clean_stem) >= 3 and clean_stem in clow) or (clow in [g.lower() for g in google_candidates])

            if is_exact_vision:
                if live_url not in vision_live_urls:
                    vision_live_urls.append(live_url)
            elif is_stem:
                if live_url not in stem_live_urls:
                    stem_live_urls.append(live_url)
            elif has_sc:
                if live_url not in script_urls:
                    script_urls.append(live_url)
            else:
                if live_url not in other_live_urls:
                    other_live_urls.append(live_url)

    final_live = []
    # Chỉ giữ lại các domain có script traffic hoặc có từ khóa khớp / vision khớp
    strict_live = [u for u in (vision_live_urls + stem_live_urls + script_urls) if u]
    for u in strict_live:
        if u not in final_live:
            final_live.append(u)

    # Nếu chưa có domain nào có script, chỉ thêm tối đa 2 domain khác để thử, tránh lang thang các web rác
    if not final_live:
        for u in other_live_urls[:2]:
            if u not in final_live:
                final_live.append(u)

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
        for c in candidates_local[:12]:
            live_url, has_sc = probe_domain_live(c)
            if live_url:
                if has_sc and live_url not in script_urls:
                    script_urls.append(live_url)
                    break
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
        window.detectIncognito = async function() {
            return { isPrivate: false, browserName: 'Chrome' };
        };
        if (window.navigator && window.navigator.webkitTemporaryStorage) {
            window.navigator.webkitTemporaryStorage.queryUsageAndQuota = function(success, error) {
                if (typeof success === 'function') success(0, 100 * 1024 * 1024 * 1024);
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

                # 3. Force detectIncognito to always return isPrivate: false
                body = re.sub(r'async\s+function\s+detectIncognito\s*\([^)]*\)\s*\{', 'async function detectIncognito() { return { isPrivate: false, browserName: "Chrome" };', body)
                body = re.sub(r'var\s+detectIncognito\s*=\s*async\s+function\s*\([^)]*\)\s*\{', 'var detectIncognito = async function() { return { isPrivate: false, browserName: "Chrome" };', body)

                # 4. Expose checkButtonClick to window
                body = body.replace('function checkButtonClick(){', 'window.__checkButtonClick = checkButtonClick; function checkButtonClick(){')

                # 5. Universal quest_info fallback across all steps and domains
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
    all_keys = re.findall(r'(?:what-on\.com|website-analytics\.net|traffic)[^"\']*?key=([a-zA-Z0-9]+)', html)
    traffic_key = None
    if all_keys:
        try:
            traffic_key = page.evaluate("""(keys) => {
                for (const k of keys) {
                    if (document.getElementById(k) || document.querySelector(`[data-key="${k}"]`) || document.querySelector(`[id*="${k}"]`)) {
                        return k;
                    }
                }
                return keys[keys.length - 1] || keys[0];
            }""", all_keys)
        except Exception:
            traffic_key = all_keys[-1]

    if not traffic_key:
        layout_blacklist = {'masthead', 'colophon', 'comments', 'site-nav', 'primary', 'secondary', 'content', 'wrapper', 'sidebar', 'footer', 'header', 'main-menu', 'wide-nav'}
        div_ids = page.evaluate("""() => Array.from(document.querySelectorAll('div[id]'))
            .map(d => d.id)
            .filter(id => (/^[a-zA-Z0-9]{5,12}$/.test(id) || /countdown|traffic|layma/i.test(id)))
        """)
        div_ids = [i for i in (div_ids or []) if i.lower() not in layout_blacklist]
        if div_ids:
            traffic_key = div_ids[0]
    log(f"[*] Detected traffic_key: {traffic_key}")

    # Kích hoạt hash ngay trên landing page nếu chưa có
    if traffic_key:
        try:
            page.evaluate(f"""() => {{
                if (!window.location.hash.includes('{traffic_key}')) {{
                    window.location.hash = '#ss-{traffic_key}';
                    window.dispatchEvent(new HashChangeEvent('hashchange'));
                }}
                const targetDiv = document.getElementById('{traffic_key}') || document.querySelector('[data-key="{traffic_key}"]');
                if (targetDiv) {{
                    targetDiv.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                }}
            }}""")
            time.sleep(1.0)
        except Exception:
            pass

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
        # Chặn toàn bộ các từ hệ thống, tiếng Anh hoặc tiếng Việt thông báo trạng thái
        blacklist = [
            'click', 'vui lòng', 'vui long', 'link', 'bước', 'buoc', 'lay ma', 'lấy mã',
            'chờ', 'seconds', 'giây', 'loading', 'success', 'successful', 'failed', 'error',
            'false', 'true', 'null', 'undefined', 'campaign', 'get code', 'get_quest_code',
            'info', 'none', 'hoàn thành', 'tiếp tục', 'quay lại', 'bài viết'
        ]
        if any(w in t.lower() for w in blacklist):
            return False
        return bool(re.match(r'^[A-Za-z0-9_\-]{4,25}$', t))

    code_found = None
    step_1_completed = False
    campaign_dead = False
    def on_resp(res):
        nonlocal code_found, step_1_completed, campaign_dead, code_from_api
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
                    # Tự động giải quyết bài toán xác minh Ontops / Best-Traffic Math Captcha
                    if "captcha/math" in u_lower or ("imageBase64" in data and "answers" in data):
                        img_b64 = data.get("imageBase64")
                        ans_choices = data.get("answers", [])
                        if img_b64 and ans_choices:
                            log(f"[*] Phát hiện bài toán xác minh Ontops Math Captcha: các lựa chọn {ans_choices}")
                            correct_ans = solve_math_captcha_gemini(img_b64, ans_choices)
                            if correct_ans is not None:
                                try:
                                    page.evaluate("""(ans) => {
                                        const opt = document.querySelector(`input[name="captchano-choice"][value="${ans}"]`);
                                        if (opt) {
                                            opt.checked = true;
                                            opt.dispatchEvent(new Event('change', { bubbles: true }));
                                            if (opt.parentElement) opt.parentElement.click();
                                        }
                                        const submitBtn = document.querySelector('#captchano-submit, .captchano-submit-btn');
                                        if (submitBtn) submitBtn.click();
                                    }""", correct_ans)
                                    log(f"[+] Đã chọn đáp án {correct_ans} và bấm Xác nhận bài toán captcha thành công!")
                                    step_1_completed = True
                                except Exception as e_click:
                                    log(f"[!] Lỗi khi click đáp án captcha: {e_click}")
                        return

                    if data.get("info") == "No Campaign" or (data.get("success") is False and "No Campaign" in str(data)):
                        campaign_dead = True
                        return
                    # Kiểm tra xem html hoặc code có chứa mã tài trợ hợp lệ không trước khi xét bước chuyển tiếp
                    raw = data.get("html") or data.get("code") or data.get("data") or data.get("c")
                    if raw and raw not in (-1, "-1", 0, "0"):
                        val = clean_code_str(raw)
                        if is_valid_sponsor_code(val):
                            code_found = val
                            code_from_api = True
                            log(f"🎉 EXTRACTED SPONSOR CODE FROM API: {code_found}")
                            return
                        else:
                            log(f"[*] API intermediate message: {val}")

                    # Xác nhận hoàn thành Bước 1 thành công
                    if data.get("success") is True and (data.get("id") or "vui lòng" in str(data.get("html", "")).lower() or data.get("code") in (-1, "-1", 0, "0")):
                        step_1_completed = True
                        log(f"[+] Widget API xác nhận hoàn thành Bước 1 (id={data.get('id')}): {data.get('html')}")
                        return
                    if data.get("success") is False:
                        log(f"[*] Widget API thông báo chưa lấy được: {data.get('info')}")
                        return
                    return

                # Text / Regex fallback CHỈ áp dụng khi response trả về raw text không phải JSON
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
                f"[id='{tk}'] [role='button']",
                f"[id='{tk}'] .traffic-button",
                f"[id='{tk}'] .whatoncode",
                f"[id='{tk}'] span",
                f"[id='{tk}'] div",
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
            "button:has-text('LẤY MÃ')", "div:has-text('LẤY MÃ')", "span:has-text('LẤY MÃ')",
            "button:has-text('LAY MA')", "div:has-text('LAY MA')",
            "button:has-text('LẤY CODE')", "div:has-text('LẤY CODE')",
            "button:has-text('GET CODE')", "div:has-text('GET CODE')",
            "button:has-text('NHẬN MÃ')", "div:has-text('NHẬN MÃ')",
            "button:has-text('LẤY PASS')",
            "button:has-text('LẤY KEY')",
            "button:has-text('BẤM VÀO ĐÂY')",
            "button:has-text('XEM MÃ')",
            "button:has-text('TIẾP TỤC')",
            "button:has-text('CONTINUE')",
            ".completed", "[class*='completed']",
            "[data-traffic]", "[data-quest]", "[data-code]"
        ])
        return sel_list

    def find_mission_button(timeout_sec=5.0):
        nonlocal traffic_key
        start_t = time.time()
        banned_hrefs = [
            '/go/', '/goto/', '/out/', '/redirect/', '/link/', 'login', 'signin', 'sign-in',
            'register', 'signup', 'sign-up', 'account', 'auth', 'cart', 'checkout', 'manclub'
        ]
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
                        is_banned = False
                        try:
                            tag_name = loc.evaluate("el => el.tagName.toLowerCase()")
                            if tag_name == "a":
                                href = (loc.get_attribute("href") or "").lower()
                                if any(b in href for b in banned_hrefs):
                                    is_banned = True
                        except Exception:
                            pass
                        if not is_banned:
                            return loc
                except Exception:
                    pass

            # Priority 2.5: Semantic Heuristics & Geometry Inspection (Chống DOM Drift khi class đổi)
            try:
                semantic_matched = page.evaluate("""() => {
                    const textRegex = /(?:l[ấa]y\\s*m[ãa]|lay\\s*ma|get\\s*code|nh[ậa]n\\s*m[ãa]|l[ấa]y\\s*pass|l[ấa]y\\s*key|click\\s*v[àa]o\\s*đ[âa]y|b[ấa]m\\s*v[àa]o\\s*đ[âa]y|nh[ậa]n\\s*code|ti[ếe]p\\s*t[ụu]c|continue|traffic|countdown)/i;
                    const banned = ['/go/', '/goto/', '/out/', '/redirect/', '/link/', 'login', 'signin', 'register', 'signup', 'account', 'auth', 'cart', 'checkout', 'manclub'];

                    // Quét toàn bộ button, role=button, input[type=button/submit] và thẻ có tương tác
                    const elements = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"], a, div[onclick], div[data-time], div[id]'));
                    let bestEl = null;
                    let bestScore = -1;

                    for (const el of elements) {
                        if (el.tagName.toLowerCase() === 'a') {
                            const href = (el.getAttribute('href') || '').toLowerCase();
                            if (banned.some(b => href.includes(b))) continue;
                        }
                        const txt = (el.innerText || el.textContent || el.value || '').trim();
                        const idStr = (el.id || '').toLowerCase();
                        const classStr = (el.className || '').toString().toLowerCase();

                        let score = 0;
                        if (textRegex.test(txt)) score += 60;
                        if (idStr.includes('traffic') || idStr.includes('whaton') || idStr.includes('layma') || idStr.includes('code')) score += 40;
                        if (classStr.includes('traffic') || classStr.includes('whaton') || classStr.includes('completed')) score += 40;
                        if (el.hasAttribute('data-time') || el.hasAttribute('data-code') || el.hasAttribute('data-key')) score += 50;

                        // Kiểm tra kích thước hình học (nút thật phải hiển thị trên màn hình, không phải tracking pixel)
                        const rect = el.getBoundingClientRect();
                        if (rect.width >= 40 && rect.height >= 18 && rect.top >= 0) {
                            score += 20;
                        } else if (rect.width === 0 || rect.height === 0) {
                            score = -1;
                        }

                        if (score > bestScore && score >= 50) {
                            bestScore = score;
                            bestEl = el;
                        }
                    }

                    if (bestEl) {
                        bestEl.scrollIntoView({ behavior: 'instant', block: 'center' });
                        bestEl.setAttribute('data-link4m-matched', 'true');
                        return true;
                    }
                    return false;
                }""")
                if semantic_matched:
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
            if not step_1_completed:
                # Kiểm tra lại xem localStorage có quest_info chưa trước khi chuyển bài viết
                has_q = page.evaluate("""() => {
                    for (let k in localStorage) {
                        if (k.includes('quest') || k.includes('traffic')) {
                            try {
                                const v = JSON.parse(localStorage.getItem(k));
                                if (v && (v.id || v.traffic_session)) return true;
                            } catch (e) {}
                        }
                    }
                    return false;
                }""")
                if not has_q:
                    log("[!] Bước 1 chưa được xác nhận hoàn tất (chưa có quest_info trong localStorage). Không chuyển sang Bước 2!")
                    break
                else:
                    step_1_completed = True

            article = None
            try:
                # If page is on an unwanted /go/ or login URL, return to sponsor homepage first
                curr_url = page.url.lower()
                if any(b in curr_url for b in ['/go/', '/goto/', 'login', 'signin', 'register', 'account']):
                    log(f"[*] Page currently on non-article URL ({page.url}), returning to {sponsor_url}")
                    page.goto(sponsor_url, wait_until="domcontentloaded", timeout=25000)
                    time.sleep(1.0)
            except Exception:
                pass

            try:
                article_candidates = page.evaluate("""(sp_url) => {
                    const host = new URL(sp_url).hostname.replace(/^www\\./, '').toLowerCase();
                    const banned = [
                        'wp-admin', 'wp-login', 'login', 'signin', 'sign-in', 'register', 'signup', 'sign-up',
                        '/go/', '/goto/', '/out/', '/redirect/', '/link/', 'cart', 'checkout', 'account', 'auth',
                        'contact', 'about', 'policy', 'terms', 'privacy', 'feed', 'sitemap', 'tracking', 'cdn-cgi',
                        'wp-content', 'wp-includes'
                    ];

                    const isValidArticle = (u) => {
                        try {
                            const parsed = new URL(u, window.location.href);
                            const pHost = parsed.hostname.replace(/^www\\./, '').toLowerCase();
                            if (pHost !== host) return false;
                            const p = parsed.pathname.toLowerCase();
                            if (p.length < 5) return false;
                            if (banned.some(b => p.includes(b))) return false;
                            if (/\\.(?:jpg|jpeg|png|webp|svg|gif|css|js|ico|pdf|zip|mp4)$/i.test(p)) return false;
                            return true;
                        } catch (e) { return false; }
                    };

                    const candidates = [];
                    const selectors = [
                        'article a[href]', '.post a[href]', '.entry-title a[href]', 'main a[href]',
                        'h1 a[href]', 'h2 a[href]', 'h3 a[href]', '.news-item a[href]', '.blog-item a[href]',
                        '.content a[href]', 'a[href]'
                    ];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(a => {
                            try {
                                const href = a.href.split('#')[0].replace(/\\/$/, '');
                                if (isValidArticle(href)) {
                                    const path = new URL(href).pathname.toLowerCase();
                                    let score = 0;
                                    const slugParts = path.split('/').filter(Boolean);
                                    const lastSlug = slugParts[slugParts.length - 1] || '';
                                    if (lastSlug.includes('-')) score += 50;
                                    if (lastSlug.split('-').length >= 3) score += 50;
                                    if (sel.startsWith('article') || sel.startsWith('.post') || sel.startsWith('h2')) score += 30;
                                    if (path.includes('game') || path.includes('bai') || path.includes('tin') || path.includes('post') || path.includes('news') || path.includes('danh-gia') || path.includes('huong-dan')) score += 30;
                                    candidates.push({ href: href, score: score });
                                }
                            } catch (e) {}
                        });
                    }

                    candidates.sort((a, b) => b.score - a.score);
                    return Array.from(new Set(candidates.map(c => c.href)));
                }""", sponsor_url)
            except Exception:
                article_candidates = []

            # Python fallback if JS article extraction yielded nothing
            if not article_candidates:
                try:
                    import urllib.request as u_req
                    from urllib.parse import urljoin as u_join, urlparse as u_parse
                    import re as py_re
                    sp_req = u_req.Request(sponsor_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
                    sp_html = u_req.urlopen(sp_req, timeout=10).read().decode('utf-8', errors='ignore')
                    raw_links = py_re.findall(r'href=[\'"]([^\'"]+)[\'"]', sp_html)
                    py_banned = [
                        'wp-admin', 'wp-login', 'login', 'signin', 'sign-in', 'register', 'signup', 'sign-up',
                        '/go/', '/goto/', '/out/', '/redirect/', '/link/', 'cart', 'checkout', 'account', 'auth',
                        'contact', 'about', 'policy', 'terms', 'privacy', 'feed', 'sitemap', 'tracking', 'cdn-cgi',
                        'wp-content', 'wp-includes'
                    ]
                    sp_host = u_parse(sponsor_url).netloc.replace('www.', '').lower()
                    py_cands = []
                    for rl in raw_links:
                        full_u = u_join(sponsor_url, rl).split('#')[0].rstrip('/')
                        pu = u_parse(full_u)
                        if pu.netloc.replace('www.', '').lower() != sp_host:
                            continue
                        p_low = pu.path.lower()
                        if len(p_low) < 5 or any(b in p_low for b in py_banned):
                            continue
                        if py_re.search(r'\.(?:jpg|jpeg|png|webp|svg|gif|css|js|ico|pdf|zip|mp4)$', p_low):
                            continue
                        slug_parts = [s for s in p_low.split('/') if s]
                        last_slug = slug_parts[-1] if slug_parts else ''
                        score = 0
                        if '-' in last_slug: score += 50
                        if len(last_slug.split('-')) >= 3: score += 50
                        if any(w in p_low for w in ['game', 'bai', 'tin', 'post', 'news', 'danh-gia', 'huong-dan']): score += 30
                        py_cands.append((score, full_u))
                    py_cands.sort(key=lambda x: x[0], reverse=True)
                    seen_py = set()
                    article_candidates = [u for sc, u in py_cands if not (u in seen_py or seen_py.add(u))]
                except Exception as py_err:
                    log(f"[!] Fallback python article scraping error: {py_err}")

            for cand in (article_candidates or []):
                if cand not in visited and not any(cand.endswith(ext) for ext in [".jpg", ".png", ".webp", ".css", ".js", ".svg"]):
                    article = cand
                    visited.add(cand)
                    break

            if not article or article == sponsor_url:
                if article_candidates:
                    article = article_candidates[0]
                else:
                    article = sponsor_url.rstrip("/")
            
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

        has_landing_traffic = False
        try:
            has_landing_traffic = page.evaluate("""() => {
                const el = document.querySelector('[id*="ss-"], [data-key], [id*="traffic-button"], .traffic-button, .whatoncode, [class*="whatoncode"]');
                if (el) return true;
                const scripts = Array.from(document.querySelectorAll('script')).map(s => s.src || s.getAttribute('data-rocket-src') || '');
                return scripts.some(src => src.includes('service-v') || src.includes('what-on') || src.includes('traffic') || src.includes('website-analytics'));
            }""")
        except Exception:
            pass

        btn = find_mission_button(timeout_sec=7.0 if has_landing_traffic else 4.5)
        # Step 2 article fallback retry if button not found on initial article
        if (not btn or btn.count() == 0) and step == 2 and article_candidates:
            log(f"[*] Step 2: Nút chưa thấy trên bài viết đầu, đang thử các bài viết nội bộ khác...")
            for fallback_art in (article_candidates or []):
                if fallback_art not in visited:
                    visited.add(fallback_art)
                    art_url = f"{fallback_art}#ss-{traffic_key}" if traffic_key else fallback_art
                    log(f"[*] Thử bài viết tiếp theo cho Bước 2: {art_url}")
                    try:
                        page.goto(art_url, wait_until="domcontentloaded", timeout=25000)
                        time.sleep(1.5)
                        prep()
                        btn = find_mission_button(timeout_sec=5.0)
                        if btn and btn.count() > 0:
                            log(f"[+] Tìm thấy nút Bước 2 thành công trên: {art_url}")
                            break
                    except Exception:
                        pass

        if (not btn or btn.count() == 0) and step == 1:
            if has_landing_traffic:
                log(f"[*] Step 1: Phát hiện script/khung nhiệm vụ trên trang đích! Đang cuộn trang kỹ để kích hoạt nút...")
                for scroll_round in range(5):
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.8)
                        page.evaluate("if (typeof forceShowButton === 'function') forceShowButton();")
                        btn = find_mission_button(timeout_sec=3.0)
                        if btn and btn.count() > 0:
                            log(f"[+] Tìm thấy nút nhiệm vụ trên trang đích sau khi cuộn trang!")
                            break
                    except Exception:
                        pass
            else:
                log(f"[*] Step 1: Nút chưa xuất hiện trên trang đích, đang tìm bài viết nội bộ trên {sponsor_url}...")
                try:
                    art_candidates = page.evaluate("""(sp_url) => {
                        const host = new URL(sp_url).hostname.replace(/^www\\./, '').toLowerCase();
                        const banned = [
                            'wp-admin', 'wp-login', 'login', 'signin', 'sign-in', 'register', 'signup', 'sign-up',
                            '/go/', '/goto/', '/out/', '/redirect/', '/link/', 'cart', 'checkout', 'account', 'auth',
                            'contact', 'about', 'policy', 'terms', 'privacy', 'feed', 'sitemap', 'tracking', 'cdn-cgi'
                        ];
                        const candidates = [];
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
                                    const path = u.pathname.toLowerCase();
                                    if (uHost === host && path.length > 4 && !banned.some(b => path.includes(b))) {
                                        const slugParts = path.split('/').filter(Boolean);
                                        const lastSlug = slugParts[slugParts.length - 1] || '';
                                        let score = 0;
                                        if (lastSlug.includes('-')) score += 50;
                                        if (lastSlug.split('-').length >= 3) score += 50;
                                        if (sel.startsWith('article') || sel.startsWith('.post')) score += 30;
                                        candidates.push({ href: u.href.replace(/\\/$/, ''), score: score });
                                    }
                                } catch (e) {}
                            });
                        }
                        candidates.sort((a, b) => b.score - a.score);
                        return Array.from(new Set(candidates.map(c => c.href)));
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
        time.sleep(0.5)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        try:
            page.evaluate("""() => {
                if (typeof window.__checkButtonClick === 'function') window.__checkButtonClick();
                else if (typeof checkButtonClick === 'function') checkButtonClick();
                else if (typeof startCountdown === 'function') startCountdown();
            }""")
        except Exception:
            pass
        time.sleep(0.4)

        # Chờ widget khởi tạo countdown và đọc chính xác thời lượng (120s, 60s, 15s)
        sec_dur = 15 if step > 1 else 60
        for _wait_init in range(6):
            time.sleep(0.5)
            try:
                sec_dur_eval = page.evaluate(f"""() => {{
                    const el = document.getElementById('{traffic_key}');
                    if (el && el.dataset.time && parseFloat(el.dataset.time) > 0) return parseFloat(el.dataset.time);
                    if (el) {{
                        const m = (el.innerText || el.textContent || '').match(/(\\d+)\\s*(?:giây|s)/i);
                        if (m && parseFloat(m[1]) > 0) return parseFloat(m[1]);
                    }}
                    const whaton = document.querySelector('.whatoncode, [class*="whatoncode"]');
                    if (whaton) {{
                        const m = (whaton.innerText || whaton.textContent || '').match(/(\\d+)\\s*(?:giây|s)/i);
                        if (m && parseFloat(m[1]) > 0) return parseFloat(m[1]);
                    }}
                    const tfBtn = document.querySelector('#traffic-button, .traffic-button, .completed, [class*="completed"]');
                    if (tfBtn) {{
                        const m = (tfBtn.innerText || '').match(/(\\d+)\\s*(?:giây|s)/i);
                        if (m && parseFloat(m[1]) > 0) return parseFloat(m[1]);
                    }}
                    if (typeof traffic_wait_time !== 'undefined' && traffic_wait_time > 0 && {step} == 1) return parseFloat(traffic_wait_time);
                    if (typeof traffic_step_2_wait_time !== 'undefined' && traffic_step_2_wait_time > 0 && {step} > 1) return parseFloat(traffic_step_2_wait_time);
                    if (!'{traffic_key}' && typeof counter2 !== 'undefined' && counter2 !== null && counter2 > 0) return parseFloat(counter2);
                    return null;
                }}""")
                if sec_dur_eval and sec_dur_eval > 0:
                    sec_dur = sec_dur_eval
                    break
            except Exception:
                pass
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

            try:
                rem = page.evaluate(f"""() => {{
                    const el = document.getElementById('{traffic_key}');
                    if (el) {{
                        const text = el.innerText || el.textContent || '';
                        if (text.includes('Mã KM:') || text.includes('Mã:') || text.includes('Code:')) return 0.0;
                        if (el.dataset.time) {{
                            const dt = parseFloat(el.dataset.time);
                            if (!isNaN(dt)) return dt;
                        }}
                        const m = text.match(/(\\d+)\\s*s\\s*\\(/i) || text.match(/(\\d+)\\s*(?:giây|s)/i);
                        if (m) return parseFloat(m[1]);
                    }}
                    const whaton = document.querySelector('.whatoncode, [class*="whatoncode"]');
                    if (whaton) {{
                        const text = whaton.innerText || whaton.textContent || '';
                        if (text.includes('Mã KM:') || text.includes('Mã:') || text.includes('Code:')) return 0.0;
                        const m = text.match(/(\\d+)\\s*s\\s*\\(/i) || text.match(/(\\d+)\\s*(?:giây|s)/i);
                        if (m) return parseFloat(m[1]);
                    }}
                    const btn = document.querySelector("#traffic-button, .traffic-button, .completed, [class*='completed'], [id='{traffic_key}'] button");
                    if (btn) {{
                        const m = (btn.innerText || '').match(/(\\d+)\\s*(?:giây|s)/i);
                        if (m) return parseFloat(m[1]);
                    }}
                    if (!'{traffic_key}' && typeof counter2 !== 'undefined' && counter2 !== null && !isNaN(counter2)) return parseFloat(counter2);
                    return null;
                }}""")
            except Exception:
                rem = None
            if rem is None:
                elapsed = time.time() - start_step_time
                rem = max(0.0, sec_dur - elapsed)

            if rem is not None:
                if tick % 6 == 0 or rem <= 3:
                    log(f"  [Step {step}] Remaining: {int(rem)}s")
                if rem <= 0:
                    log(f"[*] Step {step}: Countdown reached 0s. Processing result...")
                    if step == 1:
                        # Chờ widget tự động gọi checkButtonClick() hoặc hoàn tất Bước 1
                        time.sleep(2.0)
                        for w_tick in range(24):
                            if code_found or campaign_dead:
                                break
                            
                            has_quest = page.evaluate("""() => {
                                for (let k in localStorage) {
                                    if (k.includes('quest') || k.includes('traffic')) {
                                        try {
                                            const v = JSON.parse(localStorage.getItem(k));
                                            if (v && (v.id || v.traffic_session)) return true;
                                        } catch (e) {}
                                    }
                                }
                                return false;
                            }""")
                            if has_quest:
                                step_1_completed = True
                                log(f"[+] Phát hiện quest_info đã được lưu vào localStorage cho Bước 2!")
                                break
                            if step_1_completed:
                                break

                            # Nếu sau 4 giây widget chưa tự gọi checkButtonClick, hỗ trợ kích hoạt an toàn
                            if w_tick in (4, 10, 16, 20):
                                log(f"[*] Step 1: Kích hoạt checkButtonClick / click nút hỗ trợ...")
                                try:
                                    page.evaluate(f"""() => {{
                                        const el = document.getElementById('{traffic_key}');
                                        if (el) {{
                                            el.dataset.loading = 'false';
                                            delete el.dataset.loaded;
                                            el.dataset.time = '0';
                                            el.dataset.click = 'true';
                                            if (typeof checkButtonClick === 'function') checkButtonClick();
                                        }}
                                        const btn = document.querySelector(".whatoncode button, [id='{traffic_key}'] button, .completed, #traffic-button");
                                        if (btn) btn.click();
                                    }}""")
                                except Exception:
                                    pass

                            # Kiểm tra xem mã có xuất hiện luôn ở bước 1 không (single-step campaign)
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

                            time.sleep(0.5)

                        log(f"[*] Step 1 finished. step_1_completed={step_1_completed}, code_found={code_found}")
                        break
                    else:
                        # Step 2: Chờ nhận mã từ API hoặc DOM
                        log(f"[*] Step 2 countdown finished! Waiting for mission code from API/DOM...")
                        time.sleep(2.0)
                        for wait_i in range(50):
                            if code_found or campaign_dead:
                                break
                            if wait_i in (4, 12, 20, 28, 36):
                                try:
                                    page.mouse.wheel(0, 100 if wait_i % 8 == 0 else -100)
                                    page.evaluate(f"""() => {{
                                        const el = document.getElementById('{traffic_key}');
                                        if (el) {{
                                            el.dataset.loading = 'false';
                                            delete el.dataset.loaded;
                                            el.dataset.time = '0';
                                            el.dataset.click = 'true';
                                            if (typeof checkButtonClick === 'function') checkButtonClick();
                                        }}
                                        const c = document.querySelector('.whatoncode button, [id=\'{traffic_key}\'] button, .completed, #traffic-button, #traffic-button-no, .traffic-button-no');
                                        if (c && (!c.innerText || !c.innerText.includes('Mã KM'))) c.click();
                                    }}""")
                                except Exception:
                                    pass

                            # Thử trực tiếp gọi endpoint API lấy mã với quest_info từ localStorage nếu sau 5s chưa có mã
                            if wait_i == 8 and not code_found:
                                try:
                                    fb_code = page.evaluate(f"""async () => {{
                                        for (let k in localStorage) {{
                                            if (k.includes('quest') || k.includes('traffic')) {{
                                                try {{{{
                                                    const q = JSON.parse(localStorage.getItem(k));
                                                    if (q && q.id) {{
                                                        const eps = [
                                                            'https://s1.what-on.com/widget/get_quest_code.html?id=' + q.id + '&traffic_session=' + (q.traffic_session || '') + '&key={traffic_key}',
                                                            '/widget/get_quest_code.html?id=' + q.id + '&traffic_session=' + (q.traffic_session || '') + '&key={traffic_key}',
                                                            'https://website-analytics.net/widget/get_quest_code.html?id=' + q.id + '&traffic_session=' + (q.traffic_session || '') + '&key={traffic_key}'
                                                        ];
                                                        for (const ep of eps) {{
                                                            try {{
                                                                const r = await fetch(ep, {{ credentials: 'include' }});
                                                                if (r.ok) {{
                                                                    const res = await r.json();
                                                                    if (res && res.html && !res.html.includes('Vui lòng')) return res.html;
                                                                    if (res && res.code && res.code != -1) return res.code;
                                                                }}
                                                            }} catch (e) {{}}
                                                        }}
                                                    }}
                                                }} catch (e) {{{{}}}}
                                            }}
                                        }}
                                        return null;
                                    }}""")
                                    if fb_code:
                                        cl = clean_code_str(fb_code)
                                        if is_valid_sponsor_code(cl):
                                            code_found = cl
                                            log(f"🎉 EXTRACTED SPONSOR CODE VIA ACTIVE STEP 2 FETCH: {code_found}")
                                            break
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

                            time.sleep(0.5)
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
            fallback_res = page.evaluate(f"""async () => {{
                for (let k in localStorage) {{
                    if (k.includes('quest') || k.includes('traffic')) {{
                        try {{
                            const q = JSON.parse(localStorage.getItem(k));
                            if (q && q.id) {{
                                const sess = q.traffic_session || '';
                                const endpoints = [
                                    'https://s1.what-on.com/widget/get_quest_code.html?id=' + q.id + '&traffic_session=' + sess + '&key={traffic_key}',
                                    '/widget/get_quest_code.html?id=' + q.id + '&traffic_session=' + sess + '&key={traffic_key}',
                                    'https://website-analytics.net/widget/get_quest_code.html?id=' + q.id + '&traffic_session=' + sess + '&key={traffic_key}'
                                ];
                                for (const ep of endpoints) {{
                                    try {{
                                        const r = await fetch(ep, {{ credentials: 'include' }});
                                        if (r.ok) {{
                                            const res = await r.json();
                                            if (res && res.html && !res.html.includes('Vui lòng')) return res.html;
                                            if (res && res.code && res.code != -1) return res.code;
                                        }}
                                    }} catch (err) {{}}
                                }}
                            }}
                        }} catch (e) {{}}
                    }}
                }}
                return null;
            }}""")
            if fallback_res:
                cl = clean_code_str(fallback_res)
                if is_valid_sponsor_code(cl):
                    code_found = cl
                    log(f"🎉 EXTRACTED SPONSOR CODE VIA DIRECT FALLBACK FETCH: {code_found}")
        except Exception:
            pass

    if not code_found:
        try:
            body = page.evaluate("() => document.body ? document.body.innerText : ''")
            m = re.search(r'(?:M[ãa]\s*KM|M[ãa]\s*x[áa]c\s*nh[ậa]n|Code|M[ãa])[\s\:\-]+([A-Za-z0-9]{4,15})', body or "")
            if m and is_valid_sponsor_code(m.group(1)):
                code_found = clean_code_str(m.group(1))
                log(f"[+] FOUND CODE IN BODY: {code_found}")
        except Exception:
            pass

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
