import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Tu dong chuyen sang interpreter khac neu PYTHON_311 duoc dat va ton tai.
PYTHON_311 = os.environ.get("PYTHON_311", "").strip()
if PYTHON_311 and os.path.exists(PYTHON_311) and sys.executable.lower() != PYTHON_311.lower():
    import subprocess
    cmd = [PYTHON_311] + sys.argv
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

import time
import json
import urllib.request
import ssl
from playwright.sync_api import sync_playwright

from config import CHROME_PATH, BASE_DIR, LOG_FILE, DEST_FILE, CODE_FILE, log, copy_to_clipboard, STEALTH_INIT_SCRIPT, save_destination, log_result_card
from sponsor import get_ocr, extract_domain_candidates, probe_domain_live, solve_sponsor_quest, analyze_quest_images_gemini_vision, fallback_ai_search

def is_valid_destination(u: str) -> bool:
    if not u or not u.startswith("http"):
        return False
    return not any(d in u.lower() for d in ["trafficvn.com", "trafficvn.net", "trafficvn", "about:blank", "challenges.cloudflare.com"])

def solve_trafficvn_sponsor_page(context, sponsor_url: str) -> str:
    log(f"[*] Opening sponsor site via Google Referrer: {sponsor_url}")
    page = context.new_page()

    code_found = None

    def on_res(res):
        nonlocal code_found
        if any(ep in res.url for ep in ["get_quest_code", "get_code", "ajax_code", "lay_ma", "check_code"]):
            try:
                data = res.json()
                c = data.get("code") or data.get("data") or data.get("html")
                if c and len(str(c).strip()) >= 4:
                    code_found = str(c).strip()
                    log(f"🎉 INTERCEPTED CODE FROM API: {code_found}")
            except Exception:
                pass

    page.on("response", on_res)

    try:
        page.goto(sponsor_url, wait_until="domcontentloaded", referer="https://www.google.com/", timeout=35000)
    except Exception as e:
        log(f"[!] Sponsor goto error: {e}")
        if sponsor_url.startswith("https://"):
            http_alt = sponsor_url.replace("https://", "http://", 1)
            log(f"[*] Retrying with HTTP fallback: {http_alt}")
            try:
                page.goto(http_alt, wait_until="domcontentloaded", referer="https://www.google.com/", timeout=35000)
            except Exception as e2:
                log(f"[!] HTTP retry error: {e2}")
                try: page.close()
                except Exception: pass
                return None
        else:
            try: page.close()
            except Exception: pass
            return None

    time.sleep(2)

    # Human-like scrolling to trigger widget
    log("[*] Scrolling to trigger TrafficVN widget...")
    page.evaluate("""() => {
        const s = document.getElementById('_mkm_sentinel') || document.querySelector('.mkm-sentinel, [id*="sentinel"]');
        if (s) s.scrollIntoView({ behavior: 'instant', block: 'center' });
    }""")
    for _ in range(12):
        page.mouse.wheel(0, 500)
        time.sleep(0.2)
    for _ in range(4):
        page.mouse.wheel(0, -250)
        time.sleep(0.2)
        page.mouse.wheel(0, 250)
        time.sleep(0.2)
    time.sleep(2)

    # Check for TrafficVN Shadow DOM button
    box = page.evaluate("""() => {
        const host = document.getElementById('ma_km_2026_vip') || document.querySelector('[id*="ma_km"]') || document.querySelector('[id*="_mkm_"]') || document.querySelector('[class*="mkm"]');
        if (!host || !host.shadowRoot) return null;
        const b = host.shadowRoot.querySelector('button, img, a, [role="button"], .btn');
        if (!b) return null;
        b.scrollIntoView({ behavior: 'instant', block: 'center' });
        const rect = b.getBoundingClientRect();
        return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, width: rect.width, height: rect.height };
    }""")

    clicked_button = False
    if box and box.get("width", 0) > 0:
        log(f"[+] Located Shadow DOM button at ({box['x']:.1f}, {box['y']:.1f}). Firing trusted click...")
        page.mouse.click(box['x'], box['y'])
        clicked_button = True
    else:
        btn_pierce = page.locator("#ma_km_2026_vip >> button, #ma_km_2026_vip >> img, #ma_km_2026_vip >> .btn, [id*='ma_km'] >> button, [id*='_mkm'] >> button").first
        if btn_pierce.count() > 0:
            log("[+] Piercing locator found shadow button. Clicking natively...")
            btn_pierce.click()
            clicked_button = True

    if clicked_button or page.locator("#ma_km_2026_vip, [id*='ma_km'], [id*='_mkm']").count() > 0:
        log("[*] Monitoring countdown (up to 80s)...")
        for sec in range(1, 81):
            time.sleep(1)
            shadow_info = page.evaluate("""() => {
                const host = document.getElementById('ma_km_2026_vip') || document.querySelector('[id*="ma_km"]') || document.querySelector('[id*="_mkm_"]') || document.querySelector('[class*="mkm"]');
                if (!host || !host.shadowRoot) return { text: '', html: '' };
                const inputs = Array.from(host.shadowRoot.querySelectorAll('input, [data-code], .code, #code')).map(i => i.value || i.innerText || i.dataset.code || '');
                return {
                    text: host.shadowRoot.textContent || '',
                    html: host.shadowRoot.innerHTML || '',
                    inputVal: inputs.filter(Boolean).join(' ')
                };
            }""") or {}

            shadow_text = f"{shadow_info.get('text', '')} {shadow_info.get('inputVal', '')}"
            shadow_html = shadow_info.get('html', '')

            if sec % 10 == 0 or any(kw in shadow_text.lower() for kw in ["mã", "code", "click", "bước 2", "giây"]):
                log(f"  [{sec}s] Shadow text: {repr(shadow_text[:70])}")

            # Keep countdown active with scroll
            if sec % 3 == 0:
                page.mouse.wheel(0, 150)
                time.sleep(0.1)
                page.mouse.wheel(0, -150)

            # Check if intermediate link click required (Step 2)
            if any(kw in shadow_text.lower() for kw in ["click vào trang", "bước 2", "trang bất k"]):
                log("[*] Intermediate step detected: Navigating to sub-page...")
                sub_links = page.evaluate("""() => Array.from(document.querySelectorAll('a[href^="http"]'))
                    .map(a => a.href)
                    .filter(h => !h.includes('#') && !h.includes('.jpg') && !h.includes('.png') && !h.includes('trafficvn'))
                """)
                if sub_links:
                    page.goto(sub_links[0], wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                    for _ in range(8):
                        page.mouse.wheel(0, 500)
                        time.sleep(0.3)
                    # Check if widget button exists on sub-page and click
                    sub_box = page.evaluate("""() => {
                        const h = document.getElementById('ma_km_2026_vip') || document.querySelector('[id*="ma_km"]') || document.querySelector('[id*="_mkm_"]') || document.querySelector('[class*="mkm"]');
                        if (!h || !h.shadowRoot) return null;
                        const b = h.shadowRoot.querySelector('button, img, a, [role="button"], .btn');
                        if (!b) return null;
                        b.scrollIntoView({ behavior: 'instant', block: 'center' });
                        const rect = b.getBoundingClientRect();
                        return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, width: rect.width, height: rect.height };
                    }""")
                    if sub_box and sub_box.get("width", 0) > 0:
                        log(f"[+] Found subpage Shadow DOM button at ({sub_box['x']:.1f}, {sub_box['y']:.1f}). Clicking...")
                        page.mouse.click(sub_box['x'], sub_box['y'])
                    else:
                        log("[*] Widget not found on subpage, navigating back...")
                        page.go_back(wait_until="domcontentloaded")
                        time.sleep(2)

            # Check if code appeared in shadow_text or shadow_html
            import re
            m = re.search(r'\b([A-Za-z0-9_\-]{8,25})\b', shadow_text)
            if m and any(kw in shadow_text.lower() for kw in ["mã", "code", "xác nhận", "thành công", "mã của bạn"]):
                code_candidate = m.group(1)
                if not any(w in code_candidate.lower() for w in ["lay", "nhan", "dem", "giay", "click", "trang", "buoc"]):
                    code_found = code_candidate
                    log(f"🎉 EXTRACTED CODE FROM SHADOW DOM: {code_found}")
                    break

            # Fallback: search in shadow_html for data-code or copy input
            m_html = re.search(r'(?:data-code|value)=["\']([A-Za-z0-9_\-]{6,25})["\']', shadow_html)
            if m_html:
                code_found = m_html.group(1)
                log(f"🎉 EXTRACTED CODE FROM SHADOW HTML: {code_found}")
                break

            if code_found:
                break
    else:
        # Fallback to standard sponsor quest
        log("[*] TrafficVN Shadow widget not found, trying general sponsor quest...")
        code_found = solve_sponsor_quest(context, sponsor_url)

    try: page.close()
    except Exception: pass
    return code_found

def run(target_url: str = None, headless: bool = True):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 else "https://trafficvn.com/get/MFGm2tAlcSn"

    if "--head" in sys.argv or "-w" in sys.argv or "--window" in sys.argv:
        headless = False
    elif "--headless" in sys.argv or os.environ.get("TRAFFICVN_HEADLESS") == "1":
        headless = True

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== STARTING TRAFFICVN AUTOMATION ===\n")

    log(f"[*] Target TrafficVN URL: {target_url}")
    log(f"[*] Engine starting (Headless: {headless})...")

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,850"
        ]
        if headless:
            launch_args.extend(["--headless=new", "--use-gl=angle", "--enable-webgl"])

        user_data_dir = os.path.join(BASE_DIR, "trafficvn_profile")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=CHROME_PATH,
            headless=headless,
            args=launch_args,
            viewport={"width": 1280, "height": 850},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            ignore_https_errors=True
        )

        context.add_init_script(STEALTH_INIT_SCRIPT)

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            if (navigator.storage && navigator.storage.estimate) {
                const orig = navigator.storage.estimate.bind(navigator.storage);
                navigator.storage.estimate = async () => {
                    const res = await orig();
                    return {
                        quota: Math.max(res.quota || 0, 120000000000),
                        usage: res.usage || 2000000000
                    };
                };
            }
        """)

        page = context.pages[0] if context.pages else context.new_page()
        campaign_info = {}
        final_destination_url = None

        def on_res(res):
            nonlocal final_destination_url
            if any(ep in res.url for ep in ["get_camp.php", "change_camp.php"]):
                try:
                    data = res.json()
                    log(f"[*] Camp API response ({res.url[:60]}): {data}")
                    camp = data.get("campaign") or data.get("camp") or data.get("data") or (data if ("url_img" in data or "keyword" in data) else None)
                    if camp and isinstance(camp, dict):
                        campaign_info.clear()
                        campaign_info.update(camp)
                        log(f"[+] Active Campaign: type={campaign_info.get('type')}, keyword={campaign_info.get('keyword')}, img={campaign_info.get('url_img')}")
                except Exception:
                    pass

            if any(ep in res.url for ep in ["check.php", "get_link.php"]):
                try:
                    data = res.json()
                    log(f"[+] Intercepted Verification Response: {data}")
                    u = data.get("url") or data.get("link") or data.get("dest")
                    if u and is_valid_destination(u):
                        final_destination_url = u
                        log(f"🎉 DESTINATION URL INTERCEPTED FROM API: {final_destination_url}")
                except Exception:
                    pass

        page.on("response", on_res)

        # 1. Navigate to TrafficVN
        log(f"[*] Navigating to {target_url}...")
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            log(f"[!] Navigation note: {e}")
        time.sleep(2)

        # 2. Click Pre-check button
        btn_pre = page.locator("#precheck-btn, button:has-text('Kiểm tra ngay')").first
        if btn_pre.count() > 0:
            log("[*] Clicking 'Kiểm tra ngay' via native click...")
            btn_pre.click()

        # 3. Wait for Task Area
        log("[*] Waiting for task-area to load (up to 60s)...")
        try:
            page.wait_for_selector("#task-area:not(.hidden)", timeout=60000)
            log("[+] #task-area is now active!")
        except Exception as e:
            log(f"[-] Timeout waiting for #task-area: {e}")
            context.close()
            return

        time.sleep(2)

        # 4. Resolve Campaign and Mission Code
        code_extracted = None
        for attempt in range(1, 11):
            img_url = campaign_info.get("url_img")
            keyword = campaign_info.get("keyword") or ""
            log(f"\n[*] [Attempt {attempt}/10] Processing campaign: keyword='{keyword}', img='{img_url}'")

            target_domains = []

            # Step 4a: OCR domain from image
            if img_url:
                try:
                    actual_img_url = img_url
                    if "prnt.sc" in img_url:
                        import re
                        req_p = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                        ctx_p = ssl._create_unverified_context()
                        p_html = urllib.request.urlopen(req_p, context=ctx_p, timeout=10).read().decode("utf-8", errors="ignore")
                        m_og = re.search(r'property="og:image"\s+content="([^"]+)"', p_html)
                        if m_og:
                            actual_img_url = m_og.group(1)
                            log(f"[*] Resolved prnt.sc to direct image: {actual_img_url}")

                    req = urllib.request.Request(actual_img_url, headers={"User-Agent": "Mozilla/5.0"})
                    ctx = ssl._create_unverified_context()
                    img_bytes = urllib.request.urlopen(req, context=ctx, timeout=10).read()
                    res, _ = get_ocr()(img_bytes)
                    lines = [line[1].strip() for line in (res or [])]
                    candidates = extract_domain_candidates(lines)
                    log(f"[*] OCR Candidates: {candidates}")
                    target_domains.extend(candidates)
                    # Multimodal AI Vision directly analyzes mission screenshot (Link4M parity)
                    try:
                        log("[*] 👁️ Gửi ảnh nhiệm vụ cho Gemini Multimodal Vision phân tích...")
                        g_res = analyze_quest_images_gemini_vision([img_bytes])
                        if g_res and g_res.get("target_domains"):
                            for d in g_res["target_domains"]:
                                if not any(k in d.lower() for k in ['google', 'youtube', 'facebook', 'trafficvn']):
                                    target_domains.insert(0, d.strip('/'))
                                    log(f"[+] 👁️ [Gemini Vision] Trích xuất domain: {d}")
                        if g_res and (g_res.get("domain_hint") or g_res.get("keyword")):
                            ai_doms = fallback_ai_search(g_res.get("keyword", "") or keyword, g_res.get("domain_hint", ""))
                            for d in ai_doms:
                                if not any(k in d.lower() for k in ['google', 'youtube', 'facebook', 'trafficvn']):
                                    target_domains.append(d.strip('/'))
                    except Exception as e_gem:
                        log(f"[!] Gemini Vision note: {e_gem}")

                except Exception as e:
                    log(f"[!] OCR error: {e}")

            # Step 4b: Fallback to mapped database
            db_path = os.path.join(BASE_DIR, "camps_database.json")
            if os.path.exists(db_path):
                try:
                    with open(db_path, "r", encoding="utf-8") as f_db:
                        camps_db = json.load(f_db)
                    for k, d in camps_db.items():
                        if k.lower() in keyword.lower() or keyword.lower() in k.lower():
                            if d not in target_domains:
                                target_domains.append(d)
                except Exception:
                    pass

            # Step 4c: Probe live domains (only keep domains that actually resolve and respond)
            seen = set()
            ranked_domains = []
            for d in target_domains:
                d_clean = str(d).strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
                if d_clean and d_clean not in seen and "google" not in d_clean:
                    seen.add(d_clean)
                    ranked_domains.append(d_clean)

            # Prioritize: keyword match first, then common TLDs
            kw_clean = str(keyword).lower().strip()
            def domain_score(dom):
                s = 0
                if kw_clean and kw_clean in dom:
                    s += 100
                if any(ext in dom for ext in ['.com', '.vn', '.net', '.top', '.vip']):
                    s += 10
                return s

            ranked_domains.sort(key=domain_score, reverse=True)
            log(f"[*] Ranked sponsor candidate domains: {ranked_domains[:10]}")

            live_urls = []
            for d in ranked_domains:
                res_url, has_sc = probe_domain_live(d)
                if res_url and res_url.startswith("http"):
                    if has_sc:
                        log(f"[+] FOUND WIDGET SCRIPT ON: {res_url}")
                        live_urls.insert(0, res_url)
                    elif res_url not in live_urls:
                        live_urls.append(res_url)

            log(f"[+] Verified Live Sponsor Domains: {live_urls}")

            if live_urls:
                for s_url in live_urls:
                    code_extracted = solve_trafficvn_sponsor_page(context, str(s_url))
                    if code_extracted:
                        break

            if code_extracted:
                break

            # If no code or dead sponsor domain, click #btn-change-camp
            log("[!] Sponsor domain unreachable or code extraction failed. Requesting '#btn-change-camp'...")
            prev_kw = campaign_info.get("keyword")
            prev_img = campaign_info.get("url_img")
            btn_change = page.locator("#btn-change-camp, button:has-text('Đổi nhiệm vụ'), button:has-text('Đổi link')").first
            if btn_change.count() > 0:
                btn_change.click(force=True)
                for _ in range(10):
                    time.sleep(1)
                    # Check DOM update as well
                    dom_info = page.evaluate("""() => {
                        const img = document.querySelector('#task-area img, img[src*="uploads"]');
                        const kw = document.querySelector('#task-keyword, [id*="keyword"], .keyword');
                        return {
                            img: img ? img.src : null,
                            kw: kw ? kw.innerText.trim() : null
                        };
                    }""") or {}
                    if (dom_info.get("img") and dom_info["img"] != prev_img) or (dom_info.get("kw") and dom_info["kw"] != prev_kw):
                        campaign_info["url_img"] = dom_info.get("img") or campaign_info.get("url_img")
                        campaign_info["keyword"] = dom_info.get("kw") or campaign_info.get("keyword")
                    if campaign_info.get("keyword") != prev_kw or campaign_info.get("url_img") != prev_img:
                        log(f"[+] Successfully switched campaign to: '{campaign_info.get('keyword')}', img='{campaign_info.get('url_img')}'")
                        break

        if not code_extracted:
            log("[-] Could not extract mission code after multiple attempts. Halting.")
            context.close()
            return

        log(f"\n==========================================")
        log(f"🎉 EXTRACTED MISSION CODE: {code_extracted}")
        log(f"==========================================\n")

        try:
            with open(CODE_FILE, "w", encoding="utf-8") as f_c:
                f_c.write(code_extracted)
        except Exception:
            pass

        # 5. Fill code into TrafficVN
        page.bring_to_front()
        time.sleep(1)

        code_input = page.locator("#verification-code").first
        if code_input.count() > 0:
            log(f"[+] Typing code '{code_extracted}' into #verification-code...")
            code_input.fill(code_extracted)
            code_input.dispatch_event("input")
            code_input.dispatch_event("change")
            time.sleep(1)

        # 6. Handle Cloudflare Turnstile if present
        log("[*] Checking Turnstile verification...")
        try:
            # Check if Turnstile iframe has checkbox
            ts_iframe = page.frame_locator("iframe[src*='challenges.cloudflare.com']").first
            if ts_iframe:
                cb = ts_iframe.locator("input[type='checkbox'], .ctp-checkbox-label").first
                if cb.count() > 0:
                    log("[*] Clicking Turnstile checkbox...")
                    cb.click()
                    time.sleep(2)
        except Exception:
            pass

        # Wait for submit button to be enabled
        log("[*] Waiting for #final-submit button to become enabled...")
        btn_submit = page.locator("#final-submit").first
        for _ in range(15):
            if not btn_submit.is_disabled():
                log("[+] #final-submit is enabled! Clicking...")
                btn_submit.click()
                break
            time.sleep(1)

        # 7. Wait for destination URL
        log("[*] Waiting for final destination URL unlock...")
        for _ in range(25):
            if is_valid_destination(final_destination_url):
                break
            time.sleep(1)
            # Check modal or destination box in DOM
            dest_text = page.evaluate("""() => {
                const el = document.querySelector('#ncDestUrl, .nc-dest-url, a[href*="http"]');
                return el ? (el.innerText || el.href || '') : '';
            }""")
            if is_valid_destination(dest_text):
                final_destination_url = dest_text
                break

        if is_valid_destination(final_destination_url):
            save_destination(final_destination_url)
            log_result_card(final_destination_url, "TRAFFICVN")
        else:
            log("[!] Notice: Verification submitted. Check browser window for destination link.")

        time.sleep(2)
        context.close()

        return final_destination_url if is_valid_destination(final_destination_url) else None

if __name__ == "__main__":
    run()
