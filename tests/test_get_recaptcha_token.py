import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright
import time
import json
import urllib.request

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    time.sleep(2)
    
    # Get reCAPTCHA v3 token directly from page context
    token = page.evaluate("""async () => {
        return new Promise(resolve => {
            if (!window.grecaptcha) return resolve(null);
            window.grecaptcha.ready(() => {
                window.grecaptcha.execute('6Ld2lGQtAAAAABpB73R_Ac9jslhRgfbDihXAlIUQ', { action: 'access_link_dr' })
                    .then(t => resolve(t))
                    .catch(() => resolve(null));
            });
        });
    }""")
    print('Got reCAPTCHA v3 token len:', len(token or ''))
    
    # Get keyword info and headers from page state
    info = page.evaluate("""() => {
        const d = window.__NUXT_DATA__ || [];
        return {
            rid: window.__NUXT_DATA__ ? window.__NUXT_DATA__.find(x => typeof x === 'string' && x.length === 36 && x.includes('-')) : null
        };
    }""")
    print('info:', info)
    
    b.close()
