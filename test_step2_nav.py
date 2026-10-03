import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    pg = c.new_page()
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    pg.wait_for_timeout(2000)
    
    pg.evaluate('''() => {
        localStorage.setItem('traffic_pgEZtfC6by7_quest', JSON.stringify({
            href: 'https://secgroup.vn/',
            traffic_session: 'test_session',
            id: 'test_id',
            timestamp: Date.now()
        }));
    }''')

    link = pg.locator('a[href*="dich-vu"]').first
    print('Found link! Clicking...', flush=True)
    link.click()
    pg.wait_for_timeout(4000)

    res = pg.evaluate('''() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('LẤY MÃ'));
        const el = document.getElementById('fC6by7');
        return {
            btn_exists: !!btn,
            el_exists: !!el,
            referrer: document.referrer,
            url: window.location.href
        };
    }''')
    print('AFTER CLICK LINK:', res, flush=True)
    b.close()
