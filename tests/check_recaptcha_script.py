from patchright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    
    # Load reCAPTCHA api.js cleanly
    token = page.evaluate("""async () => {
        return new Promise(resolve => {
            const s = document.createElement('script');
            s.src = 'https://www.google.com/recaptcha/api.js?render=6Ld2lGQtAAAAABpB73R_Ac9jslhRgfbDihXAlIUQ';
            s.onload = () => {
                window.grecaptcha.ready(() => {
                    window.grecaptcha.execute('6Ld2lGQtAAAAABpB73R_Ac9jslhRgfbDihXAlIUQ', { action: 'access_link_dr' })
                        .then(t => resolve(t))
                        .catch(err => resolve('ERROR: ' + err.toString()));
                });
            };
            document.head.appendChild(s);
        });
    }""")
    print('Token from clean load:', token[:40] if token else 'None')
    b.close()
