import sys, os, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

sys.path.insert(0, r'c:\Users\XUAN\.gemini\antigravity\scratch\Link4M_Bypass_Suite\src\core')
from recaptcha_solver import get_solver_instance

final_dest = None

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()

    def on_resp(res):
        global final_dest
        if any(ep in res.url for ep in ["/links/get-link-info", "/links/check-captcha", "/links/go", "/links/verify"]):
            try:
                data = res.json()
                print(f"[API RESP] {data}", flush=True)
                if data.get('url'):
                    final_dest = data['url']
            except Exception:
                pass

    pg.on('response', on_resp)

    print("Navigating to https://link4m.net/go/2kCcIqn ...", flush=True)
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)

    code = "ThIxbj"
    print(f"Filling code '{code}' into Link4M campaign form...", flush=True)

    # Fill password in form 2 and form 1
    pg.evaluate('''(c) => {
        document.querySelectorAll("input[name='password'], #password-2, #password").forEach(inp => {
            inp.value = c;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
        });
        document.querySelectorAll('#ad_banner, .modal-backdrop, [class*="overlay"]').forEach(el => el.remove());
    }''', code)

    print("Solving reCAPTCHA on Link4M form...", flush=True)
    solver = get_solver_instance()
    res = solver.solve_on_page(pg, container_selector="#main-form-2, #recaptcha-2, #main-form")
    print("Solver result:", res, flush=True)

    # Submit form
    print("Submitting campaign form...", flush=True)
    pg.evaluate('''(code) => {
        let validToken = '';
        document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
            if (el.value && el.value.length > 20) validToken = el.value;
        });

        const f2 = document.querySelector('#main-form-2');
        if (f2) {
            if (window.jQuery && typeof checkPassword === 'function') {
                window.check_form = jQuery(f2);
                try { checkPassword(); } catch (e) {}
            }
            const btn = f2.querySelector('button[type="submit"], input[type="submit"], #btn-main-2, .btn');
            if (btn) btn.click();
        }

        const f1 = document.querySelector('#main-form');
        if (f1) {
            const btn = f1.querySelector('button[type="submit"], input[type="submit"], #btn-main, .btn');
            if (btn) btn.click();
        }
    }''', code)

    print("Waiting for unlock...", flush=True)
    for _ in range(25):
        time.sleep(0.5)
        if final_dest:
            break
        ready_url = pg.evaluate("""() => {
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
        if ready_url and 'link4m' not in ready_url:
            final_dest = ready_url
            break

    print(f"\n=======================================================", flush=True)
    print(f"🎉 FINAL DESTINATION URL: {final_dest} 🎉", flush=True)
    print(f"=======================================================\n", flush=True)

    if final_dest:
        with open('destination_url.txt', 'w', encoding='utf-8') as f:
            f.write(final_dest)

    b.close()
