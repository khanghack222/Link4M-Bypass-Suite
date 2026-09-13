import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os
import time
import json
import re
import urllib.request
from playwright.sync_api import sync_playwright

from config import CHROME_PATH, ROOT_DIR, DEST_FILE, CODE_FILE, log, copy_to_clipboard
from sponsor import get_ocr, extract_domain_candidates, probe_domain_live

def is_valid_destination(u: str) -> bool:
    if not u or not u.startswith("http"):
        return False
    return not any(d in u.lower() for d in ["gtraffic.io", "client.gtraffic.io", "about:blank"])

# Known campaign sponsor mapping for instantaneous resolution
KNOWN_CAMPAIGNS = {
    "sun": "https://sunwin.sixtyseven.co.in",
    "sunwin": "https://sunwin.sixtyseven.co.in",
    "sunwi": "https://sunwin.sixtyseven.co.in",
    "fun88": "https://greenco.com.co",
    "fun": "https://greenco.com.co",
    "hitclub": "https://hitclub.com",
    "hit": "https://hitclub.com"
}

def resolve_sponsor_domain(keyword_text: str, img_url: str) -> str:
    kw_clean = (keyword_text or "").lower().strip()
    for k, domain in KNOWN_CAMPAIGNS.items():
        if k in kw_clean or kw_clean in k:
            log(f"[+] Match known campaign '{k}' from keyword '{kw_clean}' -> {domain}")
            return domain

    if not img_url:
        return None

    log(f"[*] Downloading campaign image for OCR: {img_url}")
    temp_img = os.path.join(ROOT_DIR, "data", "temp", "gtraffic_camp.png")
    os.makedirs(os.path.dirname(temp_img), exist_ok=True)
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp, open(temp_img, "wb") as f:
            f.write(resp.read())
        ocr = get_ocr()
        res, _ = ocr(temp_img)
        lines = [line[1] for line in (res or [])]
        log(f"[*] OCR extracted {len(lines)} lines from campaign image.")
        candidates = extract_domain_candidates(lines)
        if candidates:
            log(f"[*] Domain candidates from image: {candidates}")
            for c in candidates:
                live = probe_domain_live(c)
                if live:
                    return live
            return f"https://{candidates[0]}"
    except Exception as e:
        log(f"[!] OCR resolution note: {e}")
    finally:
        if os.path.exists(temp_img):
            try: os.remove(temp_img)
            except Exception: pass

    return None

def run(target_url: str = None, headless: bool = False):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "https://gtraffic.io/X3BR2OQ"

    if "--headless" in sys.argv or "-h" in sys.argv or os.environ.get("GTRAFFIC_HEADLESS") == "1":
        headless = True

    log(f"[*] Target Gtraffic URL: {target_url}")
    log(f"[*] Starting Gtraffic Autonomous Engine (Headless: {headless})...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--no-first-run"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh"
        )

        final_destination = None

        # TAB 1: Gtraffic Page
        page1 = context.new_page()
        campaign_info = {}

        def on_gtraffic_response(res):
            nonlocal final_destination
            # Capture campaign info
            if "api/url/get" in res.url:
                try:
                    data = res.json()
                    dk = data.get("data_keyword") or {}
                    campaign_info["keyword_text"] = dk.get("keyword_text", "")
                    campaign_info["source"] = dk.get("source", "")
                    log(f"[TAB 1] Active Campaign: '{campaign_info['keyword_text']}' | Image: {campaign_info['source']}")
                except Exception:
                    pass
            # Capture final tracking URL
            if any(ep in res.url for ep in ["url/tracking-url", "url/verify", "url/click"]):
                try:
                    data = res.json()
                    u = data.get("url") or data.get("link") or data.get("data") or data.get("destination")
                    if u and is_valid_destination(u):
                        final_destination = u
                        log(f"🎉 DESTINATION URL INTERCEPTED FROM API: {final_destination}")
                except Exception:
                    pass

        page1.on("response", on_gtraffic_response)

        log("[TAB 1] Navigating to Gtraffic shortlink...")
        try:
            page1.goto(target_url, wait_until="domcontentloaded", timeout=40000)
        except Exception as e:
            log(f"[!] Warning on initial goto: {e}")
        time.sleep(3)

        # Resolve sponsor domain
        kw = campaign_info.get("keyword_text", "")
        img = campaign_info.get("source", "")
        sponsor_domain = resolve_sponsor_domain(kw, img)

        if not sponsor_domain:
            log("[!] Could not determine sponsor website. Halting.")
            browser.close()
            return

        log(f"🎉 TARGET SPONSOR WEBSITE FOR GTRAFFIC: {sponsor_domain}")

        # TAB 2: Sponsor Website (Mobile Viewport to bypass anti-desktop media queries)
        page2 = context.new_page()
        page2.set_viewport_size({"width": 414, "height": 896})

        log(f"[TAB 2] Opening sponsor site via Google referrer: {sponsor_domain}")
        try:
            page2.goto(sponsor_domain, wait_until="domcontentloaded", referer="https://www.google.com/", timeout=40000)
        except Exception as e:
            log(f"[!] Warning on sponsor goto: {e}")
        time.sleep(2.5)

        # Force unhide hidden rules & clean popups
        page2.evaluate("""() => {
            document.querySelectorAll('body > *').forEach(el => {
                el.style.visibility = 'visible';
                el.style.opacity = '1';
            });
            document.querySelectorAll('.modal, .popup, #ad_banner').forEach(el => el.remove());
        }""")

        # Scroll to locate button #traffic-button-no
        log("[TAB 2] Scrolling to locate #traffic-button-no...")
        btn = page2.locator("#traffic-button-no, .traffic-button-no-container, .traffic-button-no").first
        if btn.count() == 0:
            for _ in range(10):
                page2.mouse.wheel(0, 500)
                time.sleep(0.3)
            btn = page2.locator("#traffic-button-no, .traffic-button-no-container, .traffic-button-no").first

        if btn.count() == 0:
            log("[!] #traffic-button-no not found on sponsor page.")
            try: page2.close()
            except Exception: pass
            browser.close()
            return

        btn.scroll_into_view_if_needed()
        time.sleep(1)
        try:
            page2.tap("#traffic-button-no, .traffic-button-no-container")
        except Exception:
            btn.click(force=True)

        log("⚡ KÍCH HOẠT: Đã nhấn nút 'LẤY MÃ' ➔ Bộ đếm bắt đầu chạy (~62s)!")

        extracted_code = None
        # Countdown wait loop (~65s)
        for s in range(1, 75):
            time.sleep(1)
            state = page2.evaluate("""() => {
                const b = document.getElementById('traffic-button-no');
                const c = document.getElementById('traffic-button-no__content');
                const t = (b ? b.innerText : '') || (c ? c.innerText : '');
                return t.trim();
            }""")

            if s % 10 == 0 or (s >= 55 and s % 2 == 0):
                log(f"  [Countdown] {s}s elapsed | Button: '{state[:30]}'")

            # Check if code appeared (e.g. 6-12 characters alphanum without countdown words)
            m = re.search(r'\b([A-Za-z0-9]{6,12})\b', state)
            if m and not any(w in state.lower() for w in ["giây", "s", "cho", "chờ", "vui"]):
                extracted_code = m.group(1)
                log(f"\n==========================================")
                log(f"💎 EXTRACTED GTRAFFIC CODE: {extracted_code}")
                log(f"==========================================\n")
                break

        if not extracted_code:
            # Final fallback check in DOM
            final_t = page2.evaluate("() => document.getElementById('traffic-button-no')?.innerText || ''").strip()
            m = re.search(r'\b([A-Za-z0-9]{6,12})\b', final_t)
            if m:
                extracted_code = m.group(1)
                log(f"💎 EXTRACTED CODE ON FALLBACK: {extracted_code}")

        try: page2.close()
        except Exception: pass

        if not extracted_code:
            log("[!] Could not retrieve verification code from sponsor button. Halting.")
            browser.close()
            return

        # Write code to extracted_code.txt
        try:
            with open(CODE_FILE, "w", encoding="utf-8") as fc:
                fc.write(extracted_code)
        except Exception:
            pass

        # Switch back to TAB 1 to submit code
        log("[TAB 1] Switching back to Gtraffic tab to submit code...")
        page1.bring_to_front()
        time.sleep(1)

        # Fill code
        inp = page1.locator('input[placeholder*="Nhập mã"], input[placeholder*="xác nhận"]').first
        if inp.count() > 0:
            inp.click()
            inp.fill(extracted_code)
            inp.dispatch_event("input")
            inp.dispatch_event("change")
            log(f"[+] Filled code '{extracted_code}' into Gtraffic form!")

        time.sleep(1)
        # Click submit button
        submit_btn = page1.locator('button:has-text("NHẬP MÃ XÁC NHẬN"), button:has-text("XÁC NHẬN")').first
        if submit_btn.count() > 0:
            submit_btn.click()
            log("[+] Clicked 'NHẬP MÃ XÁC NHẬN'!")

        # Wait for destination URL
        log("[*] Waiting for destination URL unlock...")
        for _ in range(20):
            time.sleep(1)
            if is_valid_destination(final_destination):
                break
            curr_url = page1.url
            if is_valid_destination(curr_url):
                final_destination = curr_url
                break

        if is_valid_destination(final_destination):
            log(f"\n==========================================")
            log(f"🎉 FINAL DESTINATION URL: {final_destination}")
            log(f"==========================================\n")
            try:
                with open(DEST_FILE, "w", encoding="utf-8") as f:
                    f.write(str(final_destination))
                desk = os.path.expanduser(r"~\Desktop\destination_url.txt")
                with open(desk, "w", encoding="utf-8") as fd:
                    fd.write(str(final_destination))
            except Exception:
                pass
            copy_to_clipboard(str(final_destination))
        else:
            log("[!] Warning: Could not unlock final destination URL from Gtraffic.")

        browser.close()

if __name__ == "__main__":
    run()
