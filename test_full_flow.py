import sys, time, json, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    
    # Init script:
    # 1. Storage quota bypass for detectIncognito
    # 2. Dynamic pageYOffset hook
    # 3. Continuous scroll event trigger every 400ms
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

    step1_done = False
    step1_quest_id = None
    final_code = None

    def on_resp(r):
        global step1_done, step1_quest_id, final_code
        if 'get_quest_code' in r.url:
            try:
                txt = r.text()
                print(f"\n[NETWORK RESP {r.status}] {r.url[:120]}", flush=True)
                print(f"BODY: {txt[:400]}", flush=True)
                data = json.loads(txt)
                if data.get('success'):
                    # Check if Step 1 response (contains id and 'Vui lòng click')
                    if 'id' in data and not step1_done:
                        step1_quest_id = data['id']
                        step1_done = True
                        print(f"\n>>> [NETWORK CONFIRMED] STEP 1 COMPLETE! ID = {step1_quest_id} <<<", flush=True)
                    # Check if Step 2 response (contains the actual code)
                    elif 'html' in data:
                        code = str(data['html']).strip()
                        if 'Vui lòng' not in code and len(code) > 0:
                            final_code = code
                            print(f"\n=======================================================", flush=True)
                            print(f"🎉 FINAL CONFIRMATION CODE RECEIVED: {final_code} 🎉", flush=True)
                            print(f"=======================================================\n", flush=True)
            except Exception as e:
                print(f"Error reading resp: {e}", flush=True)

    pg.on('response', on_resp)

    # --- STEP 1 ---
    print("Navigating to secgroup.vn...", flush=True)
    pg.goto('https://secgroup.vn', referer='https://www.google.com/')
    
    # Clean any old localStorage tokens
    pg.evaluate('() => localStorage.clear()')
    pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')

    print("Waiting for Step 1 button to appear...", flush=True)
    pg.wait_for_function('''() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('LẤY MÃ'));
        return !!btn;
    }''', timeout=20000)

    # Click Step 1 button
    pg.evaluate('''() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('LẤY MÃ'));
        if (btn) btn.click();
    }''')
    print("Clicked Step 1 button! Monitoring 60s countdown until server response...", flush=True)

    start = time.time()
    last_text = ""
    while time.time() - start < 85 and not step1_done:
        time.sleep(2)
        cur_text = pg.evaluate('''() => {
            const whaton = document.querySelector('.whatoncode');
            return whaton ? whaton.innerText : null;
        }''') or ""
        first_line = cur_text.split('\n')[0]
        if first_line != last_text:
            print(f"[{int(time.time() - start)}s] Widget: {first_line}", flush=True)
            last_text = first_line

    if not step1_done:
        print("Failed to complete Step 1!", flush=True)
        b.close()
        sys.exit(1)

    # Allow 1 second for localStorage write
    time.sleep(1)

    # --- STEP 2 ---
    target_subpage = 'https://secgroup.vn/dich-vu-cho-thue-kho-bai#ss-fC6by7'
    print(f"\n--- [STEP 2] Navigating to subpage: {target_subpage} ---", flush=True)
    pg.goto(target_subpage)
    pg.wait_for_timeout(1000)

    print("Waiting for Step 2 button to appear...", flush=True)
    pg.wait_for_function('''() => {
        const btn = document.querySelector('#fC6by7 button') || Array.from(document.querySelectorAll('button')).find(b => b.textContent && b.textContent.includes('LẤY MÃ'));
        return !!btn;
    }''', timeout=20000)

    # Click Step 2 button
    pg.evaluate('''() => {
        const btn = document.querySelector('#fC6by7 button') || Array.from(document.querySelectorAll('button')).find(b => b.textContent && b.textContent.includes('LẤY MÃ'));
        if (btn) btn.click();
    }''')
    print("Clicked Step 2 button! Monitoring 15s countdown...", flush=True)

    start2 = time.time()
    last_text2 = ""
    while time.time() - start2 < 40 and not final_code:
        time.sleep(1)
        cur_text2 = pg.evaluate('''() => {
            const whaton = document.querySelector('.whatoncode');
            return whaton ? whaton.innerText : null;
        }''') or ""
        first_line2 = cur_text2.split('\n')[0]
        if first_line2 != last_text2:
            print(f"[{int(time.time() - start2)}s STEP 2] Widget: {first_line2}", flush=True)
            last_text2 = first_line2

        if 'Mã KM:' in cur_text2:
            m = re.search(r'Mã KM:\s*([A-Za-z0-9_\-]+)', cur_text2)
            if m:
                final_code = m.group(1)
                print(f"\n🎉 CODE FROM DOM: {final_code} 🎉\n", flush=True)
                break

    print(f"\n==========================================", flush=True)
    print(f"FINAL RESULT: Code = {final_code}", flush=True)
    print(f"==========================================\n", flush=True)
    b.close()
