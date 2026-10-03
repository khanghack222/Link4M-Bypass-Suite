import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    
    # Injected hooks for both Step 1 and Step 2:
    c.add_init_script('''
        if (navigator.webkitTemporaryStorage) {
            navigator.webkitTemporaryStorage.queryUsageAndQuota = function(cb) {
                cb(0, 100 * 1024 * 1024 * 1024);
            };
        }
        let fakeY = 1000;
        Object.defineProperty(window, 'pageYOffset', {
            get: () => { fakeY += 10; return fakeY; },
            configurable: true
        });
        setInterval(() => {
            window.dispatchEvent(new Event('scroll'));
        }, 400);
    ''')
    pg = c.new_page()

    final_code = None

    def on_resp(r):
        global final_code
        if 'get_quest_code' in r.url:
            try:
                txt = r.text()
                print(f"\n[GET_QUEST_CODE RESP {r.status}] {txt[:300]}", flush=True)
                import json
                data = json.loads(txt)
                if data.get('success'):
                    html = data.get('html', '')
                    if 'Vui lòng' not in html and len(html) > 0:
                        final_code = html
                        print(f"\n==========================================", flush=True)
                        print(f"!!! SUCCESS! FINAL CODE EXTRACTED: {final_code} !!!", flush=True)
                        print(f"==========================================\n", flush=True)
            except Exception as e:
                print(f"Error reading resp: {e}", flush=True)

    pg.on('response', on_resp)

    # ================= STEP 1 =================
    print("--- [STEP 1] Navigating to secgroup.vn ---", flush=True)
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    
    for _ in range(5):
        pg.evaluate('window.scrollBy(0, 1200)')
        pg.wait_for_timeout(500)

    btn = pg.wait_for_selector('button:has-text("LẤY MÃ"), div[id] button', timeout=15000)
    btn.scroll_into_view_if_needed()
    btn.click(force=True)
    print("Clicked STEP 1 button! Waiting ~65s...", flush=True)

    # Wait until Step 1 finishes (localStorage has _quest)
    start = time.time()
    quest_data = None
    while time.time() - start < 80:
        time.sleep(2)
        quest = pg.evaluate('''() => {
            for (let k in localStorage) {
                if (k.includes('_quest')) return localStorage.getItem(k);
            }
            return null;
        }''')
        if quest:
            quest_data = quest
            print(f"Step 1 Complete! Quest Data: {quest_data}", flush=True)
            break

    if not quest_data:
        print("Failed to complete Step 1!", flush=True)
        b.close()
        sys.exit(1)

    # ================= STEP 2 =================
    # Click an internal link on secgroup.vn as instructed
    print("\n--- [STEP 2] Clicking internal link on secgroup.vn ---", flush=True)
    # Find any good internal link
    link = pg.evaluate('''() => {
        const links = Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href)
            .filter(h => h.startsWith('https://secgroup.vn/') && !h.includes('#') && h !== 'https://secgroup.vn/');
        return links.length > 0 ? links[0] : null;
    }''')
    print(f"Internal link selected: {link}", flush=True)
    if link:
        pg.goto(link)
    else:
        # Fallback to navigating to a subpage
        pg.goto('https://secgroup.vn/gioi-thieu')

    pg.wait_for_timeout(2000)
    for _ in range(5):
        pg.evaluate('window.scrollBy(0, 1200)')
        pg.wait_for_timeout(500)

    print("Waiting for STEP 2 button selector...", flush=True)
    btn2 = pg.wait_for_selector('button:has-text("LẤY MÃ"), div[id] button', timeout=15000)
    btn2.scroll_into_view_if_needed()
    btn2.click(force=True)
    print("Clicked STEP 2 button! Waiting ~20s countdown...", flush=True)

    start2 = time.time()
    while time.time() - start2 < 30 and not final_code:
        time.sleep(1)

    print(f"\nFinal code extraction result: {final_code}", flush=True)
    b.close()
