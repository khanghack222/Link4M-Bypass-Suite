import sys
import json
import urllib.parse
import asyncio
import io
import time
import random
import requests
import cv2
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# Thread pool để fetch 9 tiles song song siêu tốc
executor = ThreadPoolExecutor(max_workers=9)

def fetch_single_tile(args):
    idx, url = args
    try:
        r = requests.get(url, timeout=3)
        im = Image.open(io.BytesIO(r.content)).convert('RGB')
        arr = np.array(im)
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        mask = (hsv[:, :, 1] > 50) | (hsv[:, :, 2] < 120)
        mask_u8 = mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return (idx, 0, 0, 0)
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        num_v = len(approx)
        circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
        return (idx, num_v, round(circ, 2), round(area, 1))
    except Exception:
        return (idx, 0, 0, 0)

def find_oddoneout_index_hsv_fast(asset_urls):
    t0 = time.time()
    args_list = [(i, u) for i, u in enumerate(asset_urls)]
    tile_features = list(executor.map(fetch_single_tile, args_list))
    tile_features.sort(key=lambda x: x[0])
    
    print(f"[*] Fast Shape Analysis ({time.time()-t0:.3f}s): {[f[1] for f in tile_features]}")
    from collections import Counter
    v_counts = Counter([f[1] for f in tile_features])
    
    if len(v_counts) > 1:
        odd_v = min(v_counts.keys(), key=lambda k: v_counts[k])
        for f in tile_features:
            if f[1] == odd_v:
                print(f">>> IDENTIFIED ODD TILE: {f[0]} (Vertices={f[1]}) <<<")
                return f[0]
                
    circs = [f[2] for f in tile_features]
    med_c = np.median(circs)
    diffs = [abs(c - med_c) for c in circs]
    best_idx = int(np.argmax(diffs))
    print(f">>> FALLBACK CIRCULARITY TILE: {best_idx} <<<")
    return best_idx

async def human_move_fast(page, x1, y1, x2, y2, steps=6):
    for i in range(1, steps + 1):
        p = i / float(steps)
        cur_x = x1 + (x2 - x1) * p
        cur_y = y1 + (y2 - y1) * p
        await page.mouse.move(cur_x, cur_y)
        await asyncio.sleep(0.01)
    await page.mouse.move(x2, y2)

async def solve_qcaptcha_to_token_fast():
    parent_html = """<!DOCTYPE html>
<html>
<head>
    <title>QCaptcha Fast Solver</title>
    <script src="https://js.103-141-140-153.sslip.io/api.js" async defer></script>
</head>
<body style="margin: 0; padding: 20px;">
    <div id="qcaptcha-box" class="q-captcha"
         data-sitekey="d0c97bcc-d88c-42d1-8a0c-1180bf53e2a1"
         data-callback="onQCaptchaSuccess"
         data-lang="vi">
    </div>
    <script>
        window.onQCaptchaSuccess = function(token) {
            console.log('[PARENT WIN] Verified token:', token);
            window.__qcaptcha_token = token;
        };
    </script>
</body>
</html>
"""

    current_challenge = {}
    verified_token = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await context.new_page()

        # Stealth patch frame.js
        async def route_frame_js(route):
            res = await route.fetch()
            text = await res.text()
            text = text.replace(
                "function automationProbe() {",
                "function automationProbe() { return { artifacts: [], missingApis: [] };"
            )
            text = text.replace(
                "function webglInfo() {",
                "function webglInfo() { return { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)' };"
            )
            text = text.replace(
                "webdriver: navigator.webdriver === true,",
                "webdriver: false,"
            )
            text = text.replace(
                "untrustedEvents: behavior.untrustedEvents,",
                "untrustedEvents: 0,"
            )
            text = text.replace(
                "solveMs: Math.round(performance.now() - state.startedAt),",
                "solveMs: Math.max(5000, Math.round(performance.now() - state.startedAt)),"
            )
            text = text.replace(
                "mouseEvents: behavior.mouseEvents,",
                "mouseEvents: Math.max(88, behavior.mouseEvents),"
            )
            await route.fulfill(response=res, body=text)

        await page.route("**/frame.js", route_frame_js)

        async def on_response(res):
            nonlocal verified_token
            if any(k in res.url for k in ["verify_passive", "solve", "skip"]):
                try:
                    data = await res.json()
                    ep = res.url.split("/")[-1]
                    print(f"[*] API {ep}: {json.dumps(data, ensure_ascii=False)}", flush=True)
                    if data.get("action") == "pass" or data.get("ok") is True:
                        t = data.get("token")
                        if t: verified_token = t
                    elif data.get("type"):
                        current_challenge.clear()
                        current_challenge.update(data)
                    elif data.get("next"):
                        current_challenge.clear()
                        current_challenge.update(data.get("next"))
                    elif data.get("action") == "challenge":
                        current_challenge.clear()
                        current_challenge.update(data)
                except:
                    pass

        page.on("response", on_response)

        await page.route("https://smileitsolutions.co.in/solve-now", lambda route: route.fulfill(
            status=200, content_type="text/html", body=parent_html
        ))

        print("[*] Navigating to host page...", flush=True)
        await page.goto("https://smileitsolutions.co.in/solve-now", wait_until="load")

        frame_el = await page.wait_for_selector("iframe[title='QCaptcha']", timeout=15000)
        frame = await frame_el.content_frame()
        await frame.wait_for_selector("#box", timeout=10000)

        # Di chuyển chuột nhanh trước khi click
        await human_move_fast(page, 100, 100, 250, 250, steps=4)
        print("[*] Clicking #box...", flush=True)
        await frame.click("#box")

        for attempt in range(1, 50):
            print(f"--- [ATTEMPT {attempt}] ---", flush=True)
            for _ in range(30):
                if verified_token: break
                is_open = await frame.evaluate("() => document.getElementById('modal-host') && !document.getElementById('modal-host').hidden")
                if is_open and current_challenge: break
                await asyncio.sleep(0.1)

            if verified_token: break

            c_type = current_challenge.get("type")
            print(f"[*] Active Challenge: {c_type}", flush=True)

            if c_type == "oddoneout":
                print(f"[*] >>> SOLVING ODD-ONE-OUT <<<", flush=True)
                assets = current_challenge.get("assets", [])
                full_urls = ["https://frame.103-141-140-153.sslip.io" + a["url"] for a in assets]
                odd_idx = find_oddoneout_index_hsv_fast(full_urls)

                tile = frame.locator(f'.qc-tile[data-i="{odd_idx}"]')
                await tile.wait_for(state="visible", timeout=5000)

                tile_bb = await tile.bounding_box()
                click_x = tile_bb['x'] + tile_bb['width'] / 2 + random.uniform(-3, 3)
                click_y = tile_bb['y'] + tile_bb['height'] / 2 + random.uniform(-3, 3)
                await human_move_fast(page, 250, 250, click_x, click_y, steps=5)
                await page.mouse.click(click_x, click_y)
                print(f"[+] Clicked tile {odd_idx}!", flush=True)

                await asyncio.sleep(0.2)
                is_checked = await tile.get_attribute("aria-checked")
                if is_checked != "true":
                    await tile.click(force=True)

                # Giữ delay 1.8s ổn định cho QCaptcha server chấp nhận
                await asyncio.sleep(1.8)

                submit_btn = frame.locator("#qc-submit")
                submit_bb = await submit_btn.bounding_box()
                sub_x = submit_bb['x'] + submit_bb['width'] / 2 + random.uniform(-3, 3)
                sub_y = submit_bb['y'] + submit_bb['height'] / 2 + random.uniform(-3, 3)
                await human_move_fast(page, click_x, click_y, sub_x, sub_y, steps=4)
                await page.mouse.click(sub_x, sub_y)
                print("[*] Clicked #qc-submit! Waiting verification...", flush=True)
                await asyncio.sleep(1.2)

            else:
                print(f"[*] Skipping {c_type}...", flush=True)
                current_challenge.clear()
                try:
                    await frame.evaluate("() => { const b = document.getElementById('qc-skip'); if (b && !b.disabled) b.click(); }")
                except:
                    pass
                await asyncio.sleep(0.15)

            if verified_token: break

        for _ in range(15):
            if verified_token: break
            await asyncio.sleep(0.2)
            t = await page.evaluate("() => window.__qcaptcha_token")
            if t: verified_token = t; break

        await browser.close()
        return verified_token

def main():
    t_start = time.time()
    print("="*60)
    print("  LAYMA.NET ULTRA-FAST EXTREME BYPASS (TARGET SUB-10S)")
    print("="*60)

    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }

    # 1. Fetch Session & Campaign
    r_sess = session.post('https://api.layma.net/api/traffic/session', json={'keyToken': 'DrDltuyGD'}, headers={
        **headers, 'Referer': 'https://smileitsolutions.co.in/vi-vn'
    })
    sess_token = r_sess.json().get('sessionToken')

    r_camp = session.get(f'https://api.layma.net/api/admin/campain?keytoken=DrDltuyGD&flatform=google&waitMode=1&requiredPageVisits=1&sessionToken={sess_token}', headers={
        **headers, 'Referer': 'https://smileitsolutions.co.in/vi-vn'
    })
    camp = r_camp.json()
    traffic_id = camp.get('id')
    traffic_session_token = camp.get('trafficSessionToken')
    visit_ticket = camp.get('visitTicket')
    print(f"[+] Campaign ID: {traffic_id} | Visit Ticket: {visit_ticket}")

    widget_headers = {
        **headers,
        'Referer': 'https://smileitsolutions.co.in/vi-vn',
        'X-Traffic-Session': sess_token
    }

    # Đăng ký visit ban đầu
    session.post('https://api.layma.net/api/traffic/visit', json={
        'trafficSessionToken': traffic_session_token,
        'visitTicket': visit_ticket,
        'trafficId': traffic_id
    }, headers=widget_headers)

    # 2. Giải QCaptcha Siêu Tốc
    print("\n[+] Đang giải mã QCaptcha siêu tốc...")
    qc_token = asyncio.run(solve_qcaptcha_to_token_fast())

    if not qc_token:
        print("[-] Không lấy được QCaptcha token!")
        return

    print(f"[+] QCAPTCHA TOKEN SUCCESS ({time.time()-t_start:.2f}s)!")

    # Ping visit hoàn tất
    session.post('https://api.layma.net/api/traffic/visit', json={
        'trafficSessionToken': traffic_session_token,
        'visitTicket': visit_ticket,
        'trafficId': traffic_id
    }, headers=widget_headers)

    # 3. Gửi Token lấy Mã Code ngay lập tức (KHÔNG CHỜ ĐẾM NGƯỢC!)
    uuid_str = f"b{int(time.time()*1000)}-4a2e-89cd-123456789abc"
    payload = {
        "uuid": uuid_str,
        "browser": "Chrome",
        "browserVersion": "122.0.0.0",
        "browserMajorVersion": 122,
        "cookies": True,
        "mobile": False,
        "os": "Windows 10",
        "osVersion": "10",
        "screen": "1366 x 768",
        "referrer": "https://www.google.com/",
        "trafficId": traffic_id,
        "trafficSessionToken": traffic_session_token,
        "solution": "0",
        "qCaptchaToken": qc_token
    }

    r_code = session.post('https://api.layma.net/api/traffic/getcode', json=payload, headers=widget_headers)
    try:
        res_code = r_code.json()
        code_val = res_code.get("html") if isinstance(res_code, dict) else res_code
    except Exception:
        code_val = r_code.text

    if not code_val or "không hợp lệ" in str(code_val):
        print(f"[-] Lỗi mã: {code_val}")
        return

    print(f"\n[>>>] MÃ UNLOCK LẤY ĐƯỢC: {code_val} (Thời gian: {time.time()-t_start:.2f}s)")

    # 4. Submit Checkcode & Follow Redirect
    r_vis = session.post('https://api.layma.net/api/traffic/visitor', json={
        'browser': 'Chrome', 'browserVersion': '122.0.0.0', 'browserMajorVersion': 122,
        'cookies': True, 'mobile': False, 'os': 'Windows 10', 'osVersion': '10',
        'screen': '1366 x 768', 'token': 'Kd1onyItr', 'uuid': uuid_str
    }, headers={**headers, 'Referer': 'https://layma.net/Kd1onyItr'})

    layma_sess = r_vis.json().get('sessionToken') if r_vis.status_code == 200 else None

    check_hdr = {**headers, 'Referer': 'https://layma.net/Kd1onyItr'}
    if layma_sess:
        check_hdr['X-Traffic-Session'] = layma_sess

    check_body = {
        "Code": str(code_val).strip(),
        "Token": "Kd1onyItr",
        "CampainId": traffic_id,
        "UserAgent": headers['User-Agent'],
        "DeviceScreen": "1366 x 768",
        "FingerprintData": "",
        "HCaptchaToken": ""
    }

    r_check = session.post('https://api.layma.net/api/traffic/checkcode', json=check_body, headers=check_hdr)
    try:
        check_json = r_check.json()
        redirect_url = check_json if isinstance(check_json, str) else (check_json.get('redirectUrl') or check_json.get('RedirectUrl'))
    except Exception:
        redirect_url = r_check.text

    if redirect_url:
        if not redirect_url.startswith("http"):
            redirect_url = "https://api.layma.net" + redirect_url
        final_resp = session.get(redirect_url, headers=headers, allow_redirects=True)
        final_url = final_resp.url
        t_total = time.time() - t_start
        print("\n" + "="*70)
        print(f"    >>> BẺ KHÓA THÀNH CÔNG SIÊU TỐC TRONG {t_total:.2f} GIÂY <<<")
        print(f"    DESTINATION URL: {final_url}")
        print("="*70 + "\n")
        with open("DESTINATION_FINAL_URL.txt", "w", encoding="utf-8") as f:
            f.write(final_url)

if __name__ == "__main__":
    main()
