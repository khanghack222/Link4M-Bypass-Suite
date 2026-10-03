import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(4000)
    
    iframes = pg.evaluate('''() => {
        return Array.from(document.querySelectorAll('iframe[src*="recaptcha"]')).map(f => {
            let p = f.parentElement;
            let path = [];
            while (p && p.tagName !== 'BODY') {
                path.push((p.tagName + (p.id ? '#' + p.id : '') + (p.className ? '.' + p.className.split(' ').join('.') : '')));
                p = p.parentElement;
            }
            return {
                src: f.src.slice(0, 80),
                visible: f.offsetWidth > 0 && f.offsetHeight > 0,
                width: f.offsetWidth,
                height: f.offsetHeight,
                path: path.join(' > ')
            };
        });
    }''')
    for ifr in iframes:
        print("IFRAME:", ifr)
    b.close()
