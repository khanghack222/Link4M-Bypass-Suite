import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from recaptcha_solver import get_solver

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    
    dest_url = None
    def on_resp(res):
        global dest_url
        if any(ep in res.url for ep in ["/links/get-link-info", "/links/check-captcha", "/links/go", "/links/verify"]):
            try:
                data = res.json()
                print(f"[API RESP] {data}")
                if data.get('url'):
                    dest_url = data['url']
            except Exception:
                pass
    pg.on('response', on_resp)
    
    print("Navigating to Link4M...")
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(4000)
    
    solver = get_solver(headless=True)
    code = "GG88MM88GG88"
    
    # Fill password in form 2
    pg.evaluate('''(c) => {
        const inp = document.querySelector("#main-form-2 input[name='password'], #password-2");
        if (inp) {
            inp.value = c;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('Filled password in form-2');
        }
    }''', code)
    
    print("Solving reCAPTCHA on #main-form-2...")
    res = solver.solve_on_page(pg, container_selector="#main-form-2, #recaptcha-2")
    print("Solver result:", res)
    
    # Now submit form 2
    print("Submitting #main-form-2...")
    pg.evaluate('''() => {
        const f = document.querySelector('#main-form-2');
        if (f) {
            if (window.jQuery && typeof checkPassword === 'function') {
                window.check_form = jQuery(f);
                try { checkPassword(); } catch (e) {}
            }
            const btn = f.querySelector('button[type="submit"], input[type="submit"], #btn-main-2, .btn');
            if (btn) btn.click();
        }
    }''')
    
    pg.wait_for_timeout(5000)
    print("Final destination url:", dest_url)
    b.close()
