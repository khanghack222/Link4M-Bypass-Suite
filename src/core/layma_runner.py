import sys
import os
import time
import json
import random
import asyncio
import io
import requests
import cv2
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright

from config import CHROME_PATH, ROOT_DIR, DEST_FILE, CODE_FILE, log, copy_to_clipboard

# Configure stdout UTF-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def find_oddoneout_index_hsv(asset_urls):
    tile_features = []
    for i, u in enumerate(asset_urls):
        try:
            r = requests.get(u, timeout=10)
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            arr = np.array(im)
            hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

            # Mask out background: shape is colored or dark
            mask = (hsv[:, :, 1] > 50) | (hsv[:, :, 2] < 120)
            mask_u8 = mask.astype(np.uint8) * 255

            contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                tile_features.append((i, 0, 0, 0))
                continue

            c = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(c)
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.04 * peri, True)
            num_v = len(approx)
            circ = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
            tile_features.append((i, num_v, round(circ, 2), round(area, 1)))
        except Exception as e:
            log(f"[!] Error inspecting tile {i}: {e}")
            tile_features.append((i, 0, 0, 0))

    log(f"[*] Shape Analysis: {len(tile_features)} tiles extracted")
    for f in tile_features:
        log(f"    Tile {f[0]}: Vertices={f[1]}, Circ={f[2]}, Area={f[3]}")

    from collections import Counter
    v_counts = Counter([f[1] for f in tile_features if f[1] > 0])
    log(f"[*] Vertex distribution: {v_counts}")

    if len(v_counts) > 1:
        odd_v = min(v_counts.keys(), key=lambda k: v_counts[k])
        for f in tile_features:
            if f[1] == odd_v:
                log(f">>> IDENTIFIED ODD TILE: {f[0]} (Vertices={f[1]}) <<<")
                return f[0]

    # Fallback to circularity outlier
    circs = [f[2] for f in tile_features]
    med_c = np.median(circs) if circs else 0
    diffs = [abs(c - med_c) for c in circs]
    best_idx = int(np.argmax(diffs)) if diffs else 0
    log(f">>> FALLBACK TO CIRCULARITY: Tile {best_idx} <<<")
    return best_idx

async def human_move(page, x1, y1, x2, y2, steps=15):
    for i in range(1, steps + 1):
        p = i / float(steps)
        cur_x = x1 + (x2 - x1) * p + random.uniform(-2, 2)
        cur_y = y1 + (y2 - y1) * p + random.uniform(-2, 2)
        await page.mouse.move(cur_x, cur_y)
        await asyncio.sleep(random.uniform(0.015, 0.03))
    await page.mouse.move(x2, y2)

async def solve_qcaptcha_to_token(headless: bool = True):
    parent_html = """<!DOCTYPE html>
<html>
<head>
    <title>QCaptcha Verification</title>
    <script src="https://js.103-141-140-153.sslip.io/api.js" async defer></script>
</head>
<body style="margin: 0; padding: 50px;">
    <h2>LayMa QCaptcha Solver</h2>
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
            executable_path=CHROME_PATH,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh"
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
                "solveMs: Math.max(4500, Math.round(performance.now() - state.startedAt)),"
            )
            text = text.replace(
                "mouseEvents: behavior.mouseEvents,",
                "mouseEvents: Math.max(65, behavior.mouseEvents),"
            )
            log("[*] Stealth WebGL & automation patches successfully injected into QCaptcha frame.js")
            await route.fulfill(response=res, body=text)

        await page.route("**/frame.js", route_frame_js)

        async def on_response(res):
            nonlocal verified_token
            if any(k in res.url for k in ["verify_passive", "solve", "skip"]):
                try:
                    data = await res.json()
                    ep = res.url.split("/")[-1]
                    log(f"[API {ep}] Response: action={data.get('action')}, type={data.get('type')}, ok={data.get('ok')}")
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
                except Exception:
                    pass

        page.on("response", on_response)

        await page.route("https://smileitsolutions.co.in/solve-now", lambda route: route.fulfill(
            status=200, content_type="text/html", body=parent_html
        ))

        log("[*] Loading QCaptcha host context...")
        await page.goto("https://smileitsolutions.co.in/solve-now", wait_until="load", timeout=30000)

        frame_el = await page.wait_for_selector("iframe[title='QCaptcha']", timeout=20000)
        frame = await frame_el.content_frame()
        await frame.wait_for_selector("#box", timeout=15000)

        # Human mouse trajectory before clicking #box
        log("[*] Simulating human mouse trajectory...")
        cx, cy = 100, 100
        for _ in range(4):
            nx, ny = random.randint(200, 600), random.randint(150, 450)
            await human_move(page, cx, cy, nx, ny, steps=8)
            cx, cy = nx, ny
            await asyncio.sleep(0.1)

        log("[*] Triggering QCaptcha container (#box)...")
        await frame.click("#box")

        for attempt in range(1, 25):
            for _ in range(25):
                await asyncio.sleep(1)
                if verified_token: break
                is_open = await frame.evaluate("() => document.getElementById('modal-host') && !document.getElementById('modal-host').hidden")
                if is_open and current_challenge: break

            if verified_token: break

            c_type = current_challenge.get("type")
            log(f"[*] Challenge round {attempt}: Type '{c_type}'")

            # Human mouse movement
            cx, cy = random.randint(200, 400), random.randint(200, 400)
            for _ in range(3):
                nx, ny = random.randint(300, 800), random.randint(200, 600)
                await human_move(page, cx, cy, nx, ny, steps=6)
                cx, cy = nx, ny

            if c_type == "oddoneout":
                log("⚡ KÍCH HOẠT: Đã bắt được thử thách 'oddoneout' ➔ Khởi động HSV Contour Shape Analysis...")
                assets = current_challenge.get("assets", [])
                full_urls = ["https://frame.103-141-140-153.sslip.io" + a["url"] for a in assets]
                odd_idx = find_oddoneout_index_hsv(full_urls)

                tile = frame.locator(f'.qc-tile[data-i="{odd_idx}"]')
                await tile.wait_for(state="visible", timeout=10000)

                tile_bb = await tile.bounding_box()
                click_x = tile_bb['x'] + tile_bb['width'] / 2 + random.uniform(-4, 4)
                click_y = tile_bb['y'] + tile_bb['height'] / 2 + random.uniform(-4, 4)
                await human_move(page, cx, cy, click_x, click_y, steps=8)
                await page.mouse.click(click_x, click_y)
                log(f"[+] Clicked odd tile {odd_idx}!")

                await asyncio.sleep(0.5)
                is_checked = await tile.get_attribute("aria-checked")
                if is_checked != "true":
                    await tile.click()

                # Natural pause before submit
                await asyncio.sleep(random.uniform(2.5, 3.2))

                submit_btn = frame.locator("#qc-submit")
                submit_bb = await submit_btn.bounding_box()
                sub_x = submit_bb['x'] + submit_bb['width'] / 2 + random.uniform(-4, 4)
                sub_y = submit_bb['y'] + submit_bb['height'] / 2 + random.uniform(-4, 4)
                await human_move(page, click_x, click_y, sub_x, sub_y, steps=8)
                await page.mouse.click(sub_x, sub_y)
                log("[*] Clicked #qc-submit! Awaiting server verification token...")
            else:
                log(f"[*] Challenge is '{c_type}', skipping to locate 'oddoneout'...")
                for _ in range(5):
                    try:
                        clicked = await frame.evaluate("() => { const b = document.getElementById('qc-skip'); if (b && !b.disabled) { b.click(); return true; } return false; }")
                        if clicked:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)

            await asyncio.sleep(3.5)
            if verified_token: break

        for _ in range(8):
            if verified_token: break
            await asyncio.sleep(1)
            t = await page.evaluate("() => window.__qcaptcha_token")
            if t:
                verified_token = t
                break

        await browser.close()
        return verified_token

def extract_layma_token(u: str) -> str:
    if not u:
        return "Kd1onyItr"
    u = u.strip()
    clean = u.split("?")[0].rstrip("/")
    return clean.split("/")[-1]

def run(target_url: str = None, headless: bool = False):
    if not target_url:
        target_url = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].startswith("http") else "https://layma.net/Kd1onyItr"

    if "--headless" in sys.argv or "-h" in sys.argv or os.environ.get("LAYMA_HEADLESS") == "1":
        headless = True

    shortlink_token = extract_layma_token(target_url)
    log(f"[*] Target LayMa URL: {target_url}")
    log(f"[*] Extracted Shortlink Token: {shortlink_token}")
    log(f"[*] Initiating LayMa Autonomous Engine (Headless: {headless})...")

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    # BƯỚC 1: Khởi tạo traffic session & lấy thông tin chiến dịch
    log("\n[BƯỚC 1] Khởi tạo session & lấy thông tin chiến dịch...")
    key_token = "DrDltuyGD"
    pub_ref = "https://smileitsolutions.co.in/vi-vn"

    try:
        r_sess = session.post("https://api.layma.net/api/traffic/session", json={"keyToken": key_token}, headers={
            **headers, "Referer": pub_ref
        }, timeout=15)
        sess_token = r_sess.json().get("sessionToken")
        log(f"[+] Traffic session token: {sess_token}")
    except Exception as e:
        log(f"[!] Warning on traffic session: {e}")
        sess_token = None

    camp = None
    for retry in range(5):
        try:
            r_camp = session.get(f"https://api.layma.net/api/admin/campain?keytoken={key_token}&flatform=google&waitMode=1&requiredPageVisits=1&sessionToken={sess_token}", headers={
                **headers, "Referer": pub_ref
            }, timeout=15)
            if r_camp.status_code == 200 and r_camp.text:
                camp = r_camp.json()
                if camp.get("id"):
                    break
        except Exception as e:
            log(f"[*] Retrying campaign fetch: {e}")
        time.sleep(2)

    if not camp:
        log("[!] Không lấy được thông tin chiến dịch từ LayMa API.")
        return None

    traffic_id = camp.get("id")
    traffic_session_token = camp.get("trafficSessionToken")
    visit_ticket = camp.get("visitTicket")
    wait_seconds = camp.get("requiredWaitSeconds", 60)
    log(f"[+] Campaign ID: {traffic_id}")
    log(f"[+] Thời gian yêu cầu chờ: {wait_seconds}s")
    log(f"[+] Visit Ticket: {visit_ticket}")

    # BƯỚC 2: Tự động giải mã QCaptcha
    log("\n[BƯỚC 2] Bắt đầu tự động giải mã QCaptcha (HSV Contour Vision)...")
    start_time = time.time()
    qc_token = asyncio.run(solve_qcaptcha_to_token(headless=headless))

    if not qc_token:
        log("[!] Không lấy được QCaptcha verification token.")
        return None

    log(f"\n✔ QCAPTCHA PASS: Đã xác thực thành công QCaptcha token: {qc_token[:35]}...")

    # BƯỚC 3: Chờ đếm ngược & gửi heartbeat visit
    elapsed = time.time() - start_time
    rem_wait = max(0, int(wait_seconds - elapsed))
    log(f"\n[BƯỚC 3] Đã trôi qua {int(elapsed)}s. Cần duy trì time-on-site {rem_wait}s để hoàn tất chu kỳ...")

    widget_headers = {
        **headers,
        "Referer": pub_ref,
        "X-Traffic-Session": sess_token
    }

    try:
        session.post("https://api.layma.net/api/traffic/visit", json={
            "trafficSessionToken": traffic_session_token,
            "visitTicket": visit_ticket,
            "trafficId": traffic_id
        }, headers=widget_headers, timeout=10)
    except Exception:
        pass

    for sec in range(rem_wait, 0, -10):
        log(f"  ⌛ Đếm ngược: còn {sec}s...")
        time.sleep(min(10, sec))
        try:
            session.post("https://api.layma.net/api/traffic/visit", json={
                "trafficSessionToken": traffic_session_token,
                "visitTicket": visit_ticket,
                "trafficId": traffic_id
            }, headers=widget_headers, timeout=10)
        except Exception:
            pass

    log("[+] Hoàn tất thời gian đếm ngược hợp lệ!")

    # BƯỚC 4: Request unlock code
    log("\n[BƯỚC 4] Gửi token lấy mã code giải phóng...")
    uuid_str = f"b{int(time.time()*1000)}-4a2e-89cd-123456789abc"
    payload = {
        "uuid": uuid_str,
        "browser": "Chrome",
        "browserVersion": "124.0.0.0",
        "browserMajorVersion": 124,
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

    code_val = None
    try:
        r_code = session.post("https://api.layma.net/api/traffic/getcode", json=payload, headers=widget_headers, timeout=15)
        log(f"[+] Phản hồi getcode: {r_code.text}")
        res_code = r_code.json()
        code_val = res_code.get("html") if isinstance(res_code, dict) else res_code
    except Exception as e:
        log(f"[!] Lỗi khi request code: {e}")
        return None

    if not code_val or "không hợp lệ" in str(code_val):
        log(f"[!] Mã nhận được không hợp lệ: {code_val}")
        return None

    code_str = str(code_val).strip()
    log(f"\n💎 EXTRACTED LAYMA CODE: {code_str}\n")
    try:
        with open(CODE_FILE, "w", encoding="utf-8") as fc:
            fc.write(code_str)
    except Exception:
        pass

    # BƯỚC 5: Submit mã vào checkcode
    log(f"[BƯỚC 5] Submit mã vào https://api.layma.net/api/traffic/checkcode...")
    try:
        r_vis = session.post("https://api.layma.net/api/traffic/visitor", json={
            "browser": "Chrome", "browserVersion": "124.0.0.0", "browserMajorVersion": 124,
            "cookies": True, "mobile": False, "os": "Windows 10", "osVersion": "10",
            "screen": "1366 x 768", "token": shortlink_token, "uuid": uuid_str
        }, headers={**headers, "Referer": f"https://layma.net/{shortlink_token}"}, timeout=15)
        layma_sess = r_vis.json().get("sessionToken") if r_vis.status_code == 200 else None
    except Exception:
        layma_sess = None

    check_hdr = {**headers, "Referer": f"https://layma.net/{shortlink_token}"}
    if layma_sess:
        check_hdr["X-Traffic-Session"] = layma_sess

    check_body = {
        "Code": code_str,
        "Token": shortlink_token,
        "CampainId": traffic_id,
        "UserAgent": headers["User-Agent"],
        "DeviceScreen": "1366 x 768",
        "FingerprintData": "",
        "HCaptchaToken": ""
    }

    try:
        r_check = session.post("https://api.layma.net/api/traffic/checkcode", json=check_body, headers=check_hdr, timeout=15)
        log(f"[+] Phản hồi checkcode: HTTP {r_check.status_code} -> {r_check.text}")
        check_json = r_check.json()
        redirect_url = check_json if isinstance(check_json, str) else (check_json.get("redirectUrl") or check_json.get("RedirectUrl"))
    except Exception as e:
        log(f"[!] Lỗi khi checkcode: {e}")
        return None

    if not redirect_url:
        log("[!] Không nhận được link chuyển hướng từ checkcode.")
        return None

    if not redirect_url.startswith("http"):
        redirect_url = "https://api.layma.net" + redirect_url

    log(f"[+] Đang chuyển hướng qua: {redirect_url}...")
    try:
        final_resp = session.get(redirect_url, headers=headers, allow_redirects=True, timeout=20)
        final_url = final_resp.url
    except Exception as e:
        log(f"[!] Lỗi khi follow redirect: {e}")
        final_url = redirect_url

    log(f"\nFINAL DESTINATION URL: {final_url}\n")
    copy_to_clipboard(final_url)
    try:
        with open(DEST_FILE, "w", encoding="utf-8") as f:
            f.write(final_url)
    except Exception:
        pass

    return final_url

if __name__ == "__main__":
    run()
