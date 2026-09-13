import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import time
from playwright.sync_api import sync_playwright

from config import CHROME_PATH, BASE_DIR, LOG_FILE, DEST_FILE, CODE_FILE, log, copy_to_clipboard
from recaptcha_solver import RecaptchaAudioSolver
from sponsor import detect_sponsor_domain, solve_sponsor_quest

def is_valid_destination(u: str) -> bool:
    if not u or not u.startswith("http"):
        return False
    return not any(d in u for d in ["link4m.org", "link4m.net", "link4m.co", "link4m.me", "about:blank"])

def run(target_url: str = None, headless: bool = True):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "https://link4m.net/go/2kCcIqn"

    # Check CLI flags
    if "--head" in sys.argv:
        headless = False
    elif "--headless" in sys.argv or os.environ.get("LINK4M_HEADLESS") == "1":
        headless = True

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== STARTING DYNAMIC E2E AUTOMATION ===\n")

    log(f"[*] Target Link4M URL: {target_url}")
    log(f"[*] Starting automation engine (Headless: {headless})...")

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,720",
            "--host-resolver-rules=MAP happy.jpn.com 104.21.17.40, MAP jpn.com 54.153.56.183, MAP dawnseeker.za.com 104.21.54.177, MAP betflik24win.co 172.67.170.150, MAP what-on.com 172.67.178.139, MAP s1.what-on.com 104.21.43.112, MAP website-analytics.net 104.21.52.154"
        ]
        if headless:
            launch_args.extend([
                "--headless=new",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-webgl"
            ])

        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=headless,
            args=launch_args
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True
        )
        context.add_init_script("""
            // 1. Quota & Webdriver bypass
            if (window.navigator && window.navigator.webkitTemporaryStorage) {
                window.navigator.webkitTemporaryStorage.queryUsageAndQuota = (s) => { if (typeof s === 'function') s(0, 500*1024*1024*1024); };
            }
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // 2. Fake Google Referrer
            try {
                Object.defineProperty(document, 'referrer', {
                    get: () => 'https://www.google.com/',
                    configurable: true
                });
            } catch (e) {}

            // 3. Always Active (Anti-Blur / Anti-Tab Switch / Fake Visibility)
            try {
                Object.defineProperty(document, 'hidden', {
                    get: () => false,
                    configurable: true
                });

                Object.defineProperty(document, 'visibilityState', {
                    get: () => 'visible',
                    configurable: true
                });

                Object.defineProperty(document, 'webkitVisibilityState', {
                    get: () => 'visible',
                    configurable: true
                });

                window.hasFocus = () => true;

                const blockedEvents = [
                    'visibilitychange',
                    'webkitvisibilitychange',
                    'blur',
                    'mouseleave'
                ];

                blockedEvents.forEach(eventType => {
                    window.addEventListener(eventType, (e) => {
                        e.stopImmediatePropagation();
                    }, true);

                    document.addEventListener(eventType, (e) => {
                        e.stopImmediatePropagation();
                    }, true);
                });
            } catch (e) {}

            // 4. Anti-Headless Stealth Fingerprint
            try {
                Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth || 1280 });
                Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight || 720 });
                Object.defineProperty(screen, 'availWidth', { get: () => 1280 });
                Object.defineProperty(screen, 'availHeight', { get: () => 720 });
                Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                if (!window.chrome) window.chrome = {};
                if (!window.chrome.runtime) window.chrome.runtime = {};
            } catch (e) {}
        """)

        page_link = context.new_page()
        final_destination_url = None

        def on_new_page(new_p):
            nonlocal final_destination_url
            try:
                new_p.wait_for_load_state("domcontentloaded", timeout=15000)
                u = new_p.url
                if is_valid_destination(u):
                    final_destination_url = u
                    log(f"🎉 DESTINATION URL INTERCEPTED FROM NEW TAB: {final_destination_url}")
            except Exception:
                pass
        context.on("page", on_new_page)

        def handle_resp(res):
            nonlocal final_destination_url
            if any(ep in res.url for ep in ["/links/get-link-info", "/links/check-captcha", "/links/go", "/links/verify"]):
                try:
                    data = res.json()
                    log(f"[+] Intercepted Link4M API response: {data}")
                    u = data.get("url") or data.get("return") or data.get("link")
                    if u and is_valid_destination(u):
                        final_destination_url = u
                        log(f"🎉 DESTINATION URL INTERCEPTED FROM API: {final_destination_url}")
                except Exception:
                    pass

        page_link.on("response", handle_resp)

        solver = RecaptchaAudioSolver(headless=headless, model_name="tiny.en")

        # ⚡ TẦNG 1: TURBO DIRECT CAPTCHA EXPLOIT (Nhảy cóc 3s)
        def route_adv(route):
            log("⚡ [TURBO EXPLOIT] Chặn /api/campaign/get-advertise -> Ép Link4M kích hoạt Cổng Captcha Trực Tiếp!")
            route.abort()

        page_link.route("**/api/campaign/get-advertise", route_adv)

        try:
            page_link.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
        except Exception as e:
            log(f"[!] Warning on initial goto: {e}")

        # Chờ Cổng Captcha Trực Tiếp render đầy đủ (tối đa 6s)
        for _ in range(12):
            if page_link.locator("h4").filter(has_text="Vui lòng check captcha").count() > 0 or \
               page_link.locator("#recaptcha iframe, .g-recaptcha iframe").count() > 0:
                break
            time.sleep(0.5)

        # Kiểm tra xem Cổng Captcha Trực Tiếp đã được kích hoạt thành công chưa
        is_direct_gate = page_link.locator("h4").filter(has_text="Vui lòng check captcha").count() > 0 or \
                         (page_link.locator("#advertise-html-wrapper").count() == 0 and page_link.locator(".g-recaptcha, #recaptcha").count() > 0)

        if is_direct_gate:
            log("🚀 [TURBO EXPLOIT] Đã kích hoạt thành công Cổng Captcha Trực Tiếp (Bỏ qua 100% nhiệm vụ tìm web)!")
            for turbo_try in range(1, 3):
                try:
                    if turbo_try > 1:
                        log(f"[*] Thử lại giải Captcha Cổng Trực Tiếp (Lần {turbo_try})...")
                        page_link.reload(wait_until="domcontentloaded", timeout=20000)
                        time.sleep(2)
                    res_solve = solver.solve_on_page(page_link, timeout_sec=25)
                    log(f"[+] Turbo solver result: {res_solve}")
                    if res_solve.get("success"):
                        time.sleep(0.5)
                        page_link.evaluate("""() => {
                            if (typeof recaptcha_callback === 'function') recaptcha_callback();
                            else if (typeof checkCaptcha === 'function') checkCaptcha();
                        }""")
                        for _ in range(20):
                            if is_valid_destination(final_destination_url):
                                break
                            btn = page_link.locator(".get-link, a[class*='get-link']")
                            if btn.count() > 0:
                                href = btn.first.get_attribute("href")
                                if href and is_valid_destination(href):
                                    final_destination_url = href
                                    log(f"🎉 DESTINATION URL CAPTURED FROM BUTTON: {final_destination_url}")
                                    break
                            time.sleep(0.5)
                    if is_valid_destination(final_destination_url):
                        break
                except Exception as e:
                    log(f"[!] Turbo solver note: {e}")

        # Nếu Turbo Exploit đã lấy được link đích -> Hoàn tất!
        if is_valid_destination(final_destination_url):
            log(f"🎉🎉🎉 [TURBO WIN] VƯỢT LINK4M SIÊU TỐC TRONG 3 GIÂY: {final_destination_url}")
        else:
            # 🛡️ TẦNG 2: FALLBACK TOÀN DIỆN SANG LUỒNG WEB TÀI TRỢ (SPONSOR QUEST)
            log("[*] Chuyển tiếp sang Tầng 2: Vượt bằng luồng Web tài trợ (Sponsor Quest)...")
            try:
                page_link.unroute("**/api/campaign/get-advertise")
                page_link.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
            except Exception as e:
                log(f"[!] Reload error: {e}")

            sponsor_url = detect_sponsor_domain(page_link)
            if not sponsor_url:
                log("[!] Could not auto-detect sponsor domain. Halting.")
                browser.close()
                return

            log(f"🎉 TARGET SPONSOR WEBSITE FOR THIS MISSION: {sponsor_url}")
            code_found = solve_sponsor_quest(context, sponsor_url)
            if not code_found:
                log("[!] Could not extract mission code. Halting.")
                browser.close()
                return

            log(f"\n==========================================")
            log(f"🎉 SUCCESS! EXTRACTED SPONSOR CODE: {code_found}")
            log(f"==========================================\n")

            try:
                with open(CODE_FILE, "w", encoding="utf-8") as f_code:
                    f_code.write(code_found)
            except Exception:
                pass

            page_link.bring_to_front()
            time.sleep(0.2)

            page_link.evaluate("""(code) => {
                document.querySelectorAll("input[name='password'], input.password, #password-2, [placeholder*='Nhập mã']").forEach(inp => {
                    inp.value = code;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                });
            }""", code_found)
            log(f"[+] Filled code '{code_found}' into all Link4M inputs!")

            try:
                res_solve = solver.solve_on_page(page_link)
                log(f"[+] Smart solver result: {res_solve}")
            except Exception as e:
                log(f"[!] AI solver note: {e}")

            time.sleep(0.3)
            if not final_destination_url:
                page_link.evaluate("""() => {
                    document.querySelectorAll('.modal-backdrop, #ad_banner, [id*="google_ads"], [class*="overlay"]').forEach(el => el.remove());
                    
                    let validToken = '';
                    document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
                        if (el.value && el.value.length > 20) validToken = el.value;
                    });
                    if (validToken) {
                        document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
                            el.value = validToken;
                        });
                    }

                    if (window.jQuery) {
                        const f2 = jQuery('#main-form-2');
                        if (f2.length && typeof checkPassword === 'function') {
                            window.check_form = f2;
                            checkPassword();
                        }
                        const f1 = jQuery('#main-form');
                        if (f1.length && typeof checkPassword === 'function') {
                            window.check_form = f1;
                            checkPassword();
                        }
                    }

                    // Direct API fallback dispatch
                    const fActive = document.querySelector('#main-form-2') || document.querySelector('#main-form');
                    if (fActive) {
                        const formData = new FormData(fActive);
                        if (validToken) formData.set('g-recaptcha-response', validToken);
                        const params = new URLSearchParams(formData).toString();
                        const endpoint = (window.api_domain || 'https://s1.link4m.app') + '/links/get-link-info';
                        fetch(endpoint, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' },
                            body: params
                        }).then(r => r.json()).then(res => {
                            if (res && res.url) {
                                window.destination_url = res.url;
                                document.querySelectorAll('.get-link').forEach(a => { a.href = res.url; a.classList.remove('disabled'); });
                            }
                        }).catch(() => {});
                    }

                    if (typeof checkCaptcha === 'function') checkCaptcha();

                    document.querySelectorAll('#btn-main, #btn-continue, button[type="submit"], input[type="submit"], .btn-primary, .get-link').forEach(btn => {
                        if (!btn.classList.contains('disabled')) {
                            btn.click();
                        }
                    });
                }""")

        log("[*] Waiting for destination URL unlock...")
        for _ in range(40):
            if is_valid_destination(final_destination_url):
                break
            time.sleep(0.25)
            ready_url = page_link.evaluate("""() => {
                const btn = document.querySelector('.get-link, a#get-link, a[href*="download"], #btn-get-link, .btn-success');
                if (btn) {
                    const h = btn.getAttribute('href') || '';
                    if (h.startsWith('http') && !h.includes('link4m') && !h.includes('about:blank')) return h;
                    if (typeof btn.click === 'function' && !btn.classList.contains('disabled')) btn.click();
                }
                return null;
            }""")
            if is_valid_destination(ready_url):
                final_destination_url = ready_url
                break

        if not is_valid_destination(final_destination_url):
            alert_msg = page_link.evaluate("""() => {
                const el = document.querySelector('.ajs-message, .alertify-notifier .ajs-error, .text-danger, .alert');
                return el ? el.innerText.trim() : null;
            }""")
            if alert_msg:
                log(f"[*] Link4M page alert: {alert_msg}")

            for btn_link in page_link.locator(".get-link, a#get-link, #btn-get-link, a.btn-success").all():
                try:
                    href = btn_link.get_attribute("href") or ""
                    if is_valid_destination(href):
                        final_destination_url = href
                        break
                    btn_link.scroll_into_view_if_needed()
                    btn_link.click(force=True)
                    time.sleep(1.5)
                except Exception:
                    pass
                if is_valid_destination(page_link.url):
                    final_destination_url = page_link.url
                    break

        if is_valid_destination(final_destination_url):
            log(f"\n==========================================")
            log(f"🎉 FINAL DESTINATION URL: {final_destination_url}")
            log(f"==========================================\n")
            try:
                with open(DEST_FILE, "w", encoding="utf-8") as f:
                    f.write(str(final_destination_url))
                desk_dest = os.path.expanduser(r"~\Desktop\destination_url.txt")
                with open(desk_dest, "w", encoding="utf-8") as f_d:
                    f_d.write(str(final_destination_url))
            except Exception:
                pass
            copy_to_clipboard(str(final_destination_url))
        else:
            log("[!] Warning: Destination URL still points to link4m or not unlocked.")

        try:
            page_link.screenshot(path=os.path.join(BASE_DIR, "final_result_screen.png"))
        except Exception:
            pass

        log("[*] Full automation completed successfully.")
        time.sleep(1.5)
        browser.close()

if __name__ == "__main__":
    run()
