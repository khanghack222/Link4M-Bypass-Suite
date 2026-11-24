import sys, os
sys.stdout.reconfigure(encoding="utf-8")

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)
_ROOT_DIR = os.path.abspath(os.path.join(_CORE_DIR, "..", ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from config import ensure_python_runtime
ensure_python_runtime()

import time
import re
try:
    from patchright.sync_api import sync_playwright
    IS_PATCHRIGHT = True
except ImportError:
    from playwright.sync_api import sync_playwright
    IS_PATCHRIGHT = False

from config import CHROME_PATH, BASE_DIR, LOG_FILE, DEST_FILE, CODE_FILE, log, copy_to_clipboard, STEALTH_INIT_SCRIPT, save_destination, read_destination, log_result_card, INOOJS_EXT_PATH
from recaptcha_solver import get_solver, get_solver_instance, RecaptchaAudioSolver
from sponsor import detect_sponsor_domain, solve_sponsor_quest
try:
    from brain import get_brain
except ImportError:
    from src.core.brain import get_brain

def is_valid_destination(u: str) -> bool:
    if not u or not u.startswith("http"):
        return False
    AD_DOMAINS = [
        "link4m.org", "link4m.net", "link4m.co", "link4m.me", "about:blank",
        "zbet", "shbet", "keonhacai", "bet88", "fb88", "fun88", "w88", "bk8",
        "ku789", "sunwin", "go88", "hitclub", "b52", "rikvip", "789club",
        "website-analytics", "what-on", "iatum", "traffic.com.vn", "best-traffic",
        "catfish", "martech", "doubleclick", "googlesyndication", "adservice"
    ]
    return not any(d in u.lower() for d in AD_DOMAINS)

def run(target_url: str = None, headless: bool = True, timeout: int = None, proxy: str = None):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "https://link4m.net/go/2kCcIqn"

    # Check CLI flags
    if "--head" in sys.argv:
        headless = False
    elif "--headless" in sys.argv or os.environ.get("LINK4M_HEADLESS") == "1":
        headless = True

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== STARTING DYNAMIC E2E AUTOMATION ===\n")

    brain = get_brain()
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
            "--enable-features=DnsOverHttps",
            "--dns-over-https-templates=https://dns.google/dns-query",
            f"--host-resolver-rules={brain.get_host_resolver_rules()}"
        ]
        if not headless and os.path.exists(INOOJS_EXT_PATH):
            launch_args.extend([
                f"--disable-extensions-except={INOOJS_EXT_PATH}",
                f"--load-extension={INOOJS_EXT_PATH}"
            ])
        if headless:
            launch_args.extend([
                "--enable-webgl",
                "--autoplay-policy=no-user-gesture-required",
                "--mute-audio=false"
            ])

        user_data_dir = os.path.join(BASE_DIR, "data", "temp", "chrome_link4m_profile")
        try:
            os.makedirs(user_data_dir, exist_ok=True)
            lock_f = os.path.join(user_data_dir, "SingletonLock")
            if os.path.exists(lock_f):
                os.remove(lock_f)
        except Exception:
            pass

        proxy_cfg = {"server": proxy} if proxy else None
        browser = None
        context = None
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=CHROME_PATH if CHROME_PATH and os.path.exists(CHROME_PATH) else None,
                headless=headless,
                args=launch_args,
                proxy=proxy_cfg,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
        except Exception as e_launch:
            log(f"[*] Persistent launch fallback: {e_launch}")
            clean_args = [a for a in launch_args if not a.startswith("--load-extension") and not a.startswith("--disable-extensions")]
            browser = p.chromium.launch(
                executable_path=CHROME_PATH if CHROME_PATH and os.path.exists(CHROME_PATH) else None,
                headless=headless,
                args=clean_args,
                proxy=proxy_cfg
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
        context.add_init_script(STEALTH_INIT_SCRIPT)
        # Khóa window.jQuery và window.$ không bị yoads_network.js đánh cắp bằng noConflict(true)
        context.add_init_script("""
            let _jq_real = undefined;
            Object.defineProperty(window, 'jQuery', {
                get: () => _jq_real,
                set: (val) => {
                    if (val && typeof val.fn !== 'undefined' && !_jq_real) {
                        _jq_real = val;
                    } else if (!_jq_real) {
                        _jq_real = val;
                    }
                },
                configurable: false
            });
            Object.defineProperty(window, '$', {
                get: () => _jq_real,
                set: (val) => {
                    if (!_jq_real && val) _jq_real = val;
                },
                configurable: false
            });
        """)

        page_link = context.pages[0] if context.pages else context.new_page()
        if timeout:
            page_link.set_default_timeout(int(timeout) * 1000)
            page_link.set_default_navigation_timeout(int(timeout) * 1000)
        final_destination_url = None

        allow_intercept_new_tab = False
        def on_new_page(new_p):
            nonlocal final_destination_url
            try:
                if not allow_intercept_new_tab:
                    return
                def on_tab_nav(frame):
                    nonlocal final_destination_url
                    if frame == new_p.main_frame:
                        u = frame.url
                        if is_valid_destination(u):
                            final_destination_url = u
                            log(f"🎉 DESTINATION URL INTERCEPTED FROM NEW TAB NAV: {final_destination_url}")
                new_p.on("framenavigated", on_tab_nav)
                new_p.wait_for_load_state("domcontentloaded", timeout=15000)
                u = new_p.url
                if is_valid_destination(u):
                    final_destination_url = u
                    log(f"🎉 DESTINATION URL INTERCEPTED FROM NEW TAB: {final_destination_url}")
            except Exception:
                pass
        context.on("page", on_new_page)

        def on_main_nav(frame):
            nonlocal final_destination_url
            if frame == page_link.main_frame:
                u = frame.url
                if is_valid_destination(u):
                    final_destination_url = u
                    log(f"🎉 DESTINATION URL INTERCEPTED FROM MAIN PAGE NAV: {final_destination_url}")
        page_link.on("framenavigated", on_main_nav)

        api_rejected_captcha = False
        sponsor_campaign_detected = None
        campaign_payload = None
        def handle_resp(res):
            nonlocal final_destination_url, api_rejected_captcha, sponsor_campaign_detected, campaign_payload
            if "/campaign/get-advertise" in res.url:
                try:
                    data = res.json()
                    log(f"[+] Intercepted Link4M campaign advertise response: success={data.get('success')}")
                    if data.get("success"):
                        sponsor_campaign_detected = True
                        campaign_payload = data
                    else:
                        sponsor_campaign_detected = False
                except Exception:
                    pass
            if any(ep in res.url for ep in ["/links/get-link-info", "/links/check-captcha", "/links/go", "/links/verify", "/api/url/done", "/api/v1/links"]):
                try:
                    data = res.json()
                    log(f"[+] Intercepted Link4M API response: {data}")
                    if data.get("success") is False:
                        api_rejected_captcha = True
                    u = data.get("url") or data.get("return") or data.get("link") or data.get("redirect") or data.get("redirect_url")
                    if not u and isinstance(data.get("data"), dict):
                        u = data["data"].get("url") or data["data"].get("link")
                    elif not u and isinstance(data.get("data"), str):
                        u = data["data"]
                    if u and is_valid_destination(u):
                        final_destination_url = u
                        log(f"🎉 DESTINATION URL INTERCEPTED FROM API: {final_destination_url}")
                except Exception:
                    pass

        def handle_req(req):
            if "get-link-info" in req.url:
                try:
                    log(f"[*] Outgoing request to {req.url}: method={req.method}, headers={req.headers}, post_data={req.post_data[:200]}...")
                except Exception:
                    pass

        page_link.on("request", handle_req)
        page_link.on("response", handle_resp)

        solver = None
        def get_solver_instance():
            nonlocal solver
            if solver is None:
                solver = get_solver(headless=headless)
            return solver

        try:
            page_link.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.0)
        except Exception as e:
            log(f"[!] Warning on initial goto: {e}")

        # Chờ trang Link4M xác định nhiệm vụ tài trợ hoặc cổng captcha (tối đa 6s)
        has_sponsor_mission = False
        has_captcha_direct = False
        for _ in range(12):
            if page_link.locator("#advertise-html-wrapper img, img[src*='uploads/advertiser'], [placeholder*='Nhập mã'], #password-2, input[name='password']").count() > 0 or sponsor_campaign_detected is True:
                has_sponsor_mission = True
                break
            time.sleep(0.5)

        if not has_sponsor_mission:
            if page_link.locator("#recaptcha iframe, .g-recaptcha iframe, iframe[src*='recaptcha']").count() > 0:
                has_captcha_direct = True
        # KIỂM TRA LUỒNG: CỔNG CAPTCHA TRỰC TIẾP HAY NHIỆM VỤ WEB TÀI TRỢ
        if has_captcha_direct and not has_sponsor_mission:
            allow_intercept_new_tab = True
            # Luồng 1: Cổng Captcha Trực Tiếp (link thuần captcha không có nhà tài trợ)
            log("🚀 [DIRECT GATE] Phát hiện Link4M Cổng Trực Tiếp (Không có web tài trợ)!")
            try:
                res_solve = get_solver_instance().solve_on_page(page_link, timeout_sec=25)
                log(f"[+] Direct solver result: {res_solve}")
                if res_solve.get("success"):
                    time.sleep(0.5)
                    page_link.evaluate("""() => {
                        if (typeof recaptcha_callback === 'function') recaptcha_callback();
                        else if (typeof checkCaptcha === 'function') checkCaptcha();
                    }""")
                    for _ in range(12):
                        if is_valid_destination(final_destination_url) or api_rejected_captcha:
                            break
                        btn = page_link.locator(".get-link, a[class*='get-link']")
                        if btn.count() > 0:
                            href = btn.first.get_attribute("href")
                            if href and is_valid_destination(href):
                                final_destination_url = href
                                log(f"🎉 DESTINATION URL CAPTURED FROM BUTTON: {final_destination_url}")
                                break
                        time.sleep(0.5)
            except Exception as e:
                log(f"[!] Direct solver note: {e}")

        if not is_valid_destination(final_destination_url):
            # Luồng 2: Web Tài TrỢ (Sponsor Quest - Tiêu Chuẩn)
            log("[*] Khởi chạy Luồng Web tài trợ (Sponsor Quest)...")
            # Chờ API campaign hoàn tất trả về payload
            for _ in range(15):
                if campaign_payload or sponsor_campaign_detected is not None:
                    break
                time.sleep(0.2)

            sponsor_candidates = detect_sponsor_domain(page_link, campaign_payload=campaign_payload)
            if not sponsor_candidates:
                log("[!] Could not auto-detect sponsor domain. Halting.")
                if browser: browser.close()
                else: context.close()
                return

            if isinstance(sponsor_candidates, str):
                sponsor_candidates = [sponsor_candidates]

            log(f"🎉 TARGET SPONSOR CANDIDATES: {sponsor_candidates}")
            code_found = solve_sponsor_quest(context, sponsor_candidates)

            if not code_found:
                log("[!] Could not extract mission code. Halting.")
                if browser: browser.close()
                else: context.close()
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
            allow_intercept_new_tab = True
            time.sleep(0.2)

            page_link.evaluate("""(code) => {
                document.querySelectorAll("input[name='password'], input.password, #password-2, [placeholder*='Nhập mã']").forEach(inp => {
                    inp.value = code;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                });
            }""", code_found)
            # Gỡ bỏ các popup / overlay quảng cáo che phủ nút bấm trước khi giải captcha
            page_link.evaluate("""() => {
                document.querySelectorAll('.modal-backdrop, #ad_banner, [id*="google_ads"], [class*="overlay"], iframe[id*="aswift"]').forEach(el => el.remove());
            }""")

            # Giải reCAPTCHA chính xác trên form nhập mã (#main-form hoặc #recaptcha)
            res_solve = {}
            try:
                recaptcha_target = "#main-form, #main-form-2, #recaptcha, #recaptcha-2"
                res_solve = get_solver_instance().solve_on_page(page_link, container_selector=recaptcha_target)
                log(f"[+] Smart solver result: {res_solve}")
                if not res_solve.get("success"):
                    time.sleep(1.2)
                    res_solve = get_solver_instance().solve_on_page(page_link, container_selector=recaptcha_target)
                    log(f"[+] Smart solver retry result: {res_solve}")
            except Exception as e:
                log(f"[!] AI solver note: {e}")

            time.sleep(0.3)
            solve_tok = (res_solve or {}).get("token") or ""
            if not final_destination_url:
                page_link.evaluate("""({ code, directToken }) => {
                    document.querySelectorAll('.modal-backdrop, #ad_banner, [id*="google_ads"], [class*="overlay"]').forEach(el => el.remove());
                    
                    let validToken = directToken || '';
                    if (!validToken) {
                        document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
                            if (el.value && el.value.length > 20) validToken = el.value;
                        });
                    }

                    // 1. Điền code vào tất cả input password
                    document.querySelectorAll("input[name='password'], input.password, #password, #password-2, [placeholder*='Nhập mã']").forEach(inp => {
                        inp.value = code;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    });

                    // 2. Điền token vào tất cả textarea g-recaptcha-response
                    if (validToken) {
                        document.querySelectorAll('[name="g-recaptcha-response"], #g-recaptcha-response, #g-recaptcha-response-1, #g-recaptcha-response-2').forEach(el => {
                            el.value = validToken;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        });
                        try {
                            if (window.grecaptcha) {
                                window.grecaptcha.getResponse = (id) => validToken;
                            }
                        } catch (e) {}
                    }

                    // 3. Chọn DUY NHẤT một form hợp lệ (#main-form hoặc #main-form-2)
                    const targetForm = document.querySelector('#main-form') || document.querySelector('#main-form-2') || document.querySelector('form');
                    if (!targetForm) return;

                    // 4. Chuẩn bị FormData chuẩn xác từ form đã chọn
                    const formData = new FormData(targetForm);
                    formData.set('password', code);
                    if (validToken) {
                        formData.set('g-recaptcha-response', validToken);
                    }
                    const params = new URLSearchParams(formData).toString();
                    const endpoint = (window.api_domain || 'https://s1.link4m.app') + '/links/get-link-info';

                    // 5. Gửi DUY NHẤT 1 request fetch duy nhất (Single-Use Token Safe)
                    fetch(endpoint, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: params
                    }).then(r => r.json()).then(res => {
                        console.log('[Link4M Single-Dispatch] Result:', res);
                        if (res && res.url) {
                            window.destination_url = res.url;
                            document.querySelectorAll('.get-link, a[href*="download"]').forEach(a => {
                                a.href = res.url;
                                a.classList.remove('disabled');
                                a.removeAttribute('disabled');
                                a.innerText = 'Click vào đây để tới trang đích';
                                try { a.click(); } catch (e) {}
                            });
                        } else if (res && res.info) {
                            window.link4m_last_error = res.info;
                            console.warn('[Link4M Single-Dispatch] Rejected:', res.info);
                        }
                    }).catch(err => {
                        console.error('[Link4M Single-Dispatch] Network error:', err);
                    });
                }""", {"code": code_found, "directToken": solve_tok})

        log("[*] Waiting for destination URL unlock...")
        for _ in range(40):
            if is_valid_destination(final_destination_url):
                break
            time.sleep(0.25)
            ready_url = page_link.evaluate("""() => {
                if (window.destination_url && window.destination_url.startsWith('http') && !window.destination_url.includes('link4m')) {
                    return window.destination_url;
                }
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
            save_destination(final_destination_url, run_id=os.environ.get("BYPASS_RUN_ID"))
            log_result_card(final_destination_url, "LINK4M")
        else:
            log("[!] Warning: Destination URL still points to link4m or not unlocked.")

        try:
            page_link.screenshot(path=os.path.join(BASE_DIR, "final_result_screen.png"))
        except Exception:
            pass

        log("[*] Full automation completed successfully.")
        try:
            log(brain.get_summary_report())
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass

        if is_valid_destination(final_destination_url):
            return final_destination_url
        dest = read_destination()
        if is_valid_destination(dest):
            return dest
        return None

if __name__ == "__main__":
    run()
