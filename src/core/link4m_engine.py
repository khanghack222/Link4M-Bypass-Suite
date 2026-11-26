#!/usr/bin/env python3
"""Link4M bypass engine — luồng đã kiểm chứng end-to-end.

Nguyên tắc sống còn: mỗi lần tải trang /go/<alias>, Link4M bốc MỘT chiến dịch
(sponsor) khác nhau. Mã KM chỉ hợp lệ nếu lấy từ đúng sponsor của chính lần tải
đó. Vì vậy toàn bộ flow nằm trong MỘT lần tải trang: đọc ảnh hướng dẫn -> OCR ra
sponsor -> lấy mã -> điền mã + captcha -> đọc link đích.

Chạy:
    PYTHON_PATH=$PWD/.venv/bin/python .venv/bin/python src/core/link4m_engine.py 2kCcIqn
    ... --json          # in JSON gọn cho máy đọc
    ... --keep-open     # không đóng tab sau khi xong
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

CDP = "http://127.0.0.1:9222"
CHROME = "/usr/bin/google-chrome"
PROFILE = "/tmp/ch-profile"
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
GRID_PNG = "/tmp/grid_engine.png"
GRID_IDX = "/tmp/idx.txt"
_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("L4M_REPO") or os.path.abspath(os.path.join(_HERE, "..", ".."))
DEST_FILE = os.path.join(REPO, "destination_url.txt")

# tld hay gặp trong chiến dịch; tránh bắt nhầm đuôi file ảnh
TLD = r"(?:com|net|org|info|io|co|in|vn|app|cloud|xyz|top|site|online|pro|me|tv|cc|vip|asia|biz|link|live|shop|store|club|fun|space|website|one|bet|win|casino)"
DOMAIN_RE = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9\-]{0,30}[a-z0-9])?\.)+" + TLD + r")\b", re.I)
PATH_RE = re.compile(r"^([a-z0-9\-]{2,}(?:/[a-z0-9\-]{2,})*)/?$", re.I)
CODE_RE = re.compile(r"Mã KM\s*:\s*([A-Za-z0-9]{4,10})")
WIDGET_RE = re.compile(r"/widget/service(?:-v\d)?\.js\?key=([A-Za-z0-9]+)")


LOG_DIR = os.path.join(REPO, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "engine.log")
RESULT_FILE = os.path.join(LOG_DIR, "last_run.json")


def log(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + line + "\n")
    except Exception:
        pass


def _write_targets(path: str) -> list:
    """Run-scoped copy first, then the fixed path the JS faces still read.

    Several faces share one box; without BYPASS_RUN_ID they race on the same
    two result files and a stale win looks like a fresh one.
    """
    run_id = os.environ.get("BYPASS_RUN_ID", "").strip()
    if not run_id:
        return [path]
    stem, ext = os.path.splitext(path)
    return [f"{stem}-{run_id}{ext}", path]


def save_destination(href: str) -> None:
    if not href or not href.startswith("http"):
        return
    for path in _write_targets(DEST_FILE):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(href + "\n")
        except Exception:
            pass


def save_result(payload: dict) -> None:
    for path in _write_targets(RESULT_FILE):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ------------------------------------------------------------------ chrome
def _proxy_free_env() -> dict:
    """Môi trường sạch proxy.

    Mạng đang đặt HTTP_PROXY=127.0.0.1:8899 (proxy xoay IP Madrid). Đi qua proxy
    thì Cloudflare luôn trả màn 'Just a moment' còn đi thẳng thì link4m trả 200,
    nên Chrome phải chạy không proxy.
    """
    return {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}


def _chrome_pids() -> list[int]:
    out = subprocess.run(["pgrep", "-f", "remote-debugging-port=9222"],
                         capture_output=True, text=True).stdout.split()
    return [int(p) for p in out if p.isdigit() and int(p) != os.getpid()]


def _running_chrome_is_direct() -> bool:
    """True nếu Chrome đang chạy đã bật --no-proxy-server."""
    for pid in _chrome_pids():
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode(errors="replace")
        except Exception:
            continue
        if "--no-proxy-server" in cmd:
            return True
    return False


def _kill_chrome():
    for pid in _chrome_pids():
        try:
            os.kill(pid, 9)
        except Exception:
            pass
    time.sleep(2)


def _cdp_up() -> bool:
    import urllib.request
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        op.open(CDP + "/json/version", timeout=2).read()
        return True
    except Exception:
        return False


def ensure_chrome() -> bool:
    """Bật Chrome CDP đi THẲNG (--no-proxy-server). Trả True nếu phải tự bật.

    ``L4M_HEADLESS=1`` -> thêm ``--headless=new`` cho server không có màn hình
    (khuyến nghị vẫn chạy qua Xvfb để Chrome hành xử giống thật hơn).
    ``--no-sandbox`` luôn bật vì cần cho container/Docker.
    """
    if _cdp_up():
        if _running_chrome_is_direct():
            return False
        log("[chrome] bản đang chạy qua proxy -> restart đi thẳng")
        _kill_chrome()
    args = [CHROME, "--remote-debugging-port=9222", f"--user-data-dir={PROFILE}",
            "--no-first-run", "--no-default-browser-check", "--disable-gpu",
            "--disable-dev-shm-usage", "--no-proxy-server", "--no-sandbox",
            "--mute-audio", "--disable-background-timer-throttling",
            "--js-flags=--max-old-space-size=512",
            "--disable-features=BackForwardCache,Translate,CalculateNativeWinOcclusion",
            "--renderer-process-limit=3", "--window-size=1280,1000"]
    if os.environ.get("L4M_HEADLESS", "").strip().lower() in ("1", "true", "yes"):
        args.append("--headless=new")
    args.append("about:blank")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=_proxy_free_env())
    for _ in range(45):
        time.sleep(1)
        if _cdp_up():
            return True
    raise RuntimeError("Chrome CDP không mở được sau 45s")


# ------------------------------------------------------------------ OCR
_ocr = None


def ocr_lines(path: str) -> list[str]:
    global _ocr
    from rapidocr_onnxruntime import RapidOCR
    if _ocr is None:
        _ocr = RapidOCR()
    res, _ = _ocr(path)
    return [it[1] for it in (res or [])]


def ocr_fix(dom: str) -> list[str]:
    """Sửa lỗi OCR hay gặp: o->0, l/I->1 khi đứng cạnh chữ số (10o -> 100)."""
    out = [dom]
    for i, ch in enumerate(dom):
        near_digit = ((i and dom[i - 1].isdigit()) or (i + 1 < len(dom) and dom[i + 1].isdigit()))
        if not near_digit:
            continue
        rep = {"o": "0", "l": "1", "i": "1", "s": "5", "g": "9"}.get(ch)
        if rep:
            out += [d[:i] + rep + d[i + 1:] for d in list(out)]
    # bỏ đuôi rác kiểu "..in" / "..net."
    out += [d.strip(".-_") for d in list(out)]
    return list(dict.fromkeys(d for d in out if DOMAIN_RE.fullmatch(d)))


def sponsor_candidates(lines: list[str]) -> list[str]:
    """OCR -> danh sách URL sponsor, ưu tiên domain có path đi kèm."""
    out: list[str] = []
    seen: set[str] = set()

    def push(dom: str, path: str = ""):
        dom = dom.lower().strip(".")
        if dom.startswith("www."):
            dom = dom[4:]
        if not re.search(r"\.", dom) or len(dom) < 6:
            return
        for base in (f"https://{dom}", f"https://www.{dom}"):
            url = base + (("/" + path.strip("/")) if path else "")
            if url not in seen:
                seen.add(url)
                out.append(url)

    for raw in lines:
        low = raw.lower()
        # dòng kiểu "tylenhacai100.in > vi-vn" hoặc "ao88o.co/vi-vn"
        for m in DOMAIN_RE.finditer(low):
            tail = low[m.end():].strip()
            path = ""
            mt = re.match(r"^[\s>›»/|-]+([a-z0-9\-/_%.]{2,})", tail)
            if mt:
                cand = mt.group(1).strip("/")
                if PATH_RE.match(cand):
                    path = cand
            for dom in ocr_fix(m.group(1)):
                push(dom, path)
    # domain trần trước, có path sau (path dài dễ sai do OCR)
    out.sort(key=lambda u: u.count("/") - 2)
    return out


SEARCH_KW_RE = re.compile(r"\bt[u]?\s*khoa\s*[:：]?\s*([A-Za-z0-9_\-\.]{2,40})", re.I)
MASKED_DOMAIN_RE = re.compile(r"\b((?:[a-z0-9\-]{1,63}\.)*[a-z0-9\-]*\*[a-z0-9\-.*]*\.[a-z]{2,24})\b", re.I)


def _deaccent(text: str) -> str:
    """Bỏ dấu tiếng Việt để regex bắt được cả chữ NFD lẫn precomposed."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text or "")
                   if not unicodedata.combining(c))


def instruction_hints(text: str) -> tuple[str, str]:
    """Đọc hướng dẫn dạng chữ (campaign mới bỏ ảnh): từ khoá + domain bị che."""
    plain = _deaccent(text)
    kw = ""
    m = SEARCH_KW_RE.search(plain)
    if m:
        kw = m.group(1).strip(".,;:()[]'\"")
    mask = ""
    for mm in MASKED_DOMAIN_RE.finditer(plain.lower()):
        cand = mm.group(1).strip(".,;:")
        if "*" in cand:
            mask = cand
            break
    return kw, mask


def masked_domain_guesses(mask: str) -> list[str]:
    """Sinh domain ứng viên từ token bị che, ví dụ ``m.lotobet***.com``."""
    if not mask or "*" not in mask:
        return []
    try:
        from domain_utils import unmask_domain_candidates
        out = list(unmask_domain_candidates(mask))
    except Exception:
        out = []
    labels = mask.split(".")
    if len(labels) < 2:
        return out
    base = ".".join(labels[:-1]).replace("*", "").strip(".-")
    stems = [base]
    if base.startswith("www."):
        stems.append(base[4:])
    parts = base.split(".")
    if len(parts) > 2:
        stems.append(".".join(parts[1:]))
    for s in stems:
        if not s:
            continue
        out.extend([s, f"www.{s}"])
    return list(dict.fromkeys(d for d in out if d and DOMAIN_RE.fullmatch(d)))


def widget_keys(html: str) -> list[str]:
    return list(dict.fromkeys(WIDGET_RE.findall(html)))


def widget_key(html: str) -> str:
    ks = widget_keys(html)
    return ks[0] if ks else ""


SPONSOR_CACHE = "/tmp/l4m_sponsors.json"


def fetch_html(url: str, referer: str = "", mobile: bool = True) -> str:
    """Tải HTML bằng vân tay TLS Chrome (curl_cffi), fallback urllib.

    mobile=True là bắt buộc với sponsor kiểu m.<domain>: bản desktop thường
    không nhúng widget what-on.
    """
    headers = {"Referer": referer or "https://www.google.com/",
               "User-Agent": UA_MOBILE if mobile else UA_DESKTOP}
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, impersonate="chrome124", timeout=25, allow_redirects=True, headers=headers)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception:
        return ""


def cache_sponsor(url: str, key: str):
    try:
        data = json.load(open(SPONSOR_CACHE))
    except Exception:
        data = []
    if url not in [d.get("url") for d in data]:
        data.insert(0, {"url": url, "key": key, "ts": int(time.time())})
    try:
        json.dump(data[:20], open(SPONSOR_CACHE, "w"), ensure_ascii=False)
    except Exception:
        pass


def cached_sponsors() -> list[str]:
    try:
        return [d["url"] for d in json.load(open(SPONSOR_CACHE)) if d.get("url")]
    except Exception:
        return []


# ------------------------------------------------------------------ DOM helpers
def token_now(pg) -> str:
    try:
        vals = pg.evaluate(
            "Array.from(document.querySelectorAll('textarea[name=g-recaptcha-response]')).map(t=>t.value)")
    except Exception:
        return ""
    return max(vals, key=len) if vals else ""


def find_challenge(pg):
    for f in pg.frames:
        if "bframe" not in f.url:
            continue
        try:
            if f.locator("#rc-imageselect-target").count():
                return f
        except Exception:
            pass
    return None


def click_anchor(pg) -> bool:
    """Bấm ô checkbox reCAPTCHA của đúng widget (khớp recaptcha_key).

    Ưu tiên click bằng JS ngay trong anchor frame (ổn định hơn toạ độ, không
    lệch khi trang cuộn), fallback về mouse theo bounding box.
    """
    want = pg.evaluate("typeof recaptcha_key!=='undefined'?recaptcha_key:''")
    cand = []
    for f in pg.frames:
        if "/recaptcha/api2/anchor" not in f.url and "/recaptcha/enterprise/anchor" not in f.url:
            continue
        k = f.url.split("k=")[1].split("&")[0] if "k=" in f.url else ""
        if want and k != want:
            continue
        try:
            chk = f.locator("#recaptcha-anchor")
            if chk.count():
                chk.first.click(timeout=3000)
                log("[captcha] đã bấm checkbox (frame)")
                return True
        except Exception:
            pass
        try:
            bb = f.frame_element().bounding_box()
        except Exception:
            continue
        if bb and bb["width"] > 50:
            cand.append((bb["y"], bb))
    cand.sort(key=lambda x: x[0])
    if not cand:
        return False
    bb = cand[0][1]
    cx, cy = bb["x"] + 28, bb["y"] + bb["height"] / 2
    pg.mouse.move(cx - 40, cy - 20, steps=8)
    time.sleep(0.2)
    pg.mouse.move(cx, cy, steps=6)
    time.sleep(0.2)
    pg.mouse.click(cx, cy)
    log("[captcha] đã bấm checkbox (mouse)")
    return True


def solve_challenge(pg) -> str:
    """Giải thử thách đang hiện: audio (local) -> solver 3 tầng -> lưới ảnh."""
    try:
        from captcha_audio import solve as solve_audio
        tok = solve_audio(pg)
        if tok:
            log("[captcha] audio xong, token", len(tok))
            return tok
    except Exception as exc:
        log("[captcha] audio lỗi:", str(exc)[:80])
    try:
        from recaptcha_solver import get_solver
        res = get_solver(headless=True).solve_on_page(pg, timeout_sec=45)
        if res.get("success") and res.get("token"):
            log("[captcha] solver xong:", res.get("type"), len(res["token"]))
            return res["token"]
        log("[captcha] solver thua:", res.get("error"))
    except Exception as exc:
        log("[captcha] solver lỗi:", str(exc)[:80])
    headless = os.environ.get("L4M_HEADLESS", "").strip().lower() in ("1", "true", "yes")
    manual = os.environ.get("L4M_MANUAL_GRID", "").strip().lower() in ("1", "true", "yes")
    if headless and not manual:
        # Không có người ngồi trước màn hình: chờ index lưới 5 phút là treo job.
        log("[captcha] headless: bỏ lưới ảnh (L4M_MANUAL_GRID=1 để bật)")
        return ""
    tok = solve_grid(pg)
    if tok:
        log("[captcha] lưới ảnh xong, token", len(tok))
    return tok


GRID_PROMPT = "/tmp/grid_prompt.txt"


def grid_geometry(ch) -> tuple[int, int]:
    """Đếm số hàng/cột thật của lưới (3x3, 4x4 hoặc lưới động)."""
    try:
        g = ch.evaluate("""() => {
          const t = document.querySelector('#rc-imageselect-target table');
          if (!t) return {rows: 0, cols: 0};
          const rows = t.querySelectorAll('tr').length;
          const cols = Math.max(...[...t.querySelectorAll('tr')].map(r => r.querySelectorAll('td').length));
          return {rows, cols};
        }""")
        return int(g.get("rows") or 0), int(g.get("cols") or 0)
    except Exception:
        return 0, 0


def grid_prompt(ch) -> str:
    try:
        t = ch.locator(".rc-imageselect-desc-wrapper, .rc-imageselect-desc").first.inner_text()
        return " ".join(t.split())
    except Exception:
        return ""


def click_tiles(ch, idx: list[int], rows: int, cols: int) -> int:
    """Click theo index 1-based đọc từ ảnh chụp. Trả số tile click được."""
    n = rows * cols if rows and cols else 16
    done = 0
    for i in idx:
        if i < 1 or i > n:
            continue
        # ưu tiên tile element (ổn định hơn td), fallback td
        for sel in ("div.rc-imageselect-tile", "#rc-imageselect-target table td"):
            try:
                loc = ch.locator(sel)
                if loc.count() < i:
                    continue
                loc.nth(i - 1).click(timeout=4000)
                done += 1
                time.sleep(0.3)
                break
            except Exception:
                continue
    return done


def read_idx(path: str, n: int, cols: int = 4) -> list[int]:
    """Đọc /tmp/idx.txt: '1 4 7', '2,3' (hàng,cột), hoặc 'skip'."""
    txt = open(path).read().strip()
    if "skip" in txt.lower():
        return []
    pairs = re.findall(r"(\d+)\s*[,;x]\s*(\d+)", txt)
    if pairs:
        idx = []
        for r, c in pairs:
            idx.append((int(r) - 1) * max(cols, 1) + int(c))
        return [i for i in idx if 1 <= i <= n]
    return [int(x) for x in re.findall(r"\d+", txt) if 1 <= int(x) <= n]


def solve_grid(pg, rounds: int = 4) -> str:
    """Lưới ảnh reCAPTCHA: chụp ảnh -> agent/người đọc ghi index -> click -> verify.

    Trả token nếu giải xong, "" nếu bỏ. Lưới động (ảnh đổi sau mỗi click) được
    xử lý bằng cách chụp lại từng vòng.
    """
    for rd in range(rounds):
        ch = find_challenge(pg)
        if not ch:
            return token_now(pg)
        prompt = grid_prompt(ch)
        rows, cols = grid_geometry(ch)
        n = rows * cols if rows and cols else 16
        log(f"[grid] vòng {rd + 1}: {rows}x{cols} | yêu cầu: {prompt[:110]}")
        tiles = 0
        try:
            tiles = ch.locator("div.rc-imageselect-tile").count()
        except Exception:
            pass
        if not tiles:
            # Frame ẩn (widget thứ hai trên trang) hoặc lưới chưa render: không
            # có ảnh để đọc, chờ index 5 phút chỉ treo job.
            log("[grid] frame không có tile -> bỏ (không chờ index)")
            return ""
        shot_at = time.time()
        shot_ok = False
        for _ in range(6):
            try:
                ch.locator("#rc-imageselect-target").first.screenshot(path=GRID_PNG, timeout=15000)
                shot_ok = os.path.exists(GRID_PNG) and os.path.getmtime(GRID_PNG) >= shot_at - 1
                break
            except Exception:
                time.sleep(2)
        if not shot_ok:
            log("[grid] không chụp được ảnh lưới -> bỏ (không chờ index)")
            return ""
        try:
            with open(GRID_PROMPT, "w") as f:
                f.write(f"{prompt}\n{rows}x{cols}\n{GRID_PNG}\n")
        except Exception:
            pass
        try:
            os.unlink(GRID_IDX)
        except OSError:
            pass
        log(f"[grid] ảnh: {GRID_PNG} | gợi ý: {GRID_PROMPT} | chờ index trong {GRID_IDX}")
        idx: list[int] = []
        t0 = time.time()
        while time.time() - t0 < 300:
            if os.path.exists(GRID_IDX):
                try:
                    idx = read_idx(GRID_IDX, n, cols or 4)
                except Exception:
                    idx = []
                if idx or "skip" in open(GRID_IDX).read().lower():
                    break
            time.sleep(1)
        if not idx:
            log("[grid] không có index -> bỏ")
            return ""
        done = click_tiles(ch, idx, rows, cols)
        log(f"[grid] click {done}/{len(idx)} tile: {idx}")
        try:
            ch.locator("#recaptcha-verify-button").click(timeout=5000)
        except Exception:
            pass
        # chờ token hoặc lưới mới
        for _ in range(12):
            time.sleep(1)
            tok = token_now(pg)
            if tok and not find_challenge(pg):
                log("[grid] giải xong, token", len(tok))
                return tok
            ch2 = find_challenge(pg)
            if ch2:
                try:
                    err = ch2.locator(".rc-imageselect-incorrect-response").first.inner_text()
                except Exception:
                    err = ""
                if err:
                    log("[grid] server báo:", err[:60])
                break
    log("[grid] hết vòng")
    return token_now(pg)


# ------------------------------------------------------------------ sponsor quest
def press_widget(tab, cdp, key: str) -> bool:
    """Bấm nút LẤY MÃ. Toạ độ tính lại ngay trước khi bấm (lazy-load làm xô layout)."""
    tab.evaluate("(k)=>{const e=document.getElementById(k); if(e) e.scrollIntoView({block:'center'});}", key)
    time.sleep(1.0)
    pos = tab.evaluate(
        "(k)=>{const e=document.getElementById(k); if(!e) return null;"
        "const b=e.querySelector('button')||e; const r=b.getBoundingClientRect();"
        "return {x:r.x+r.width/2,y:r.y+r.height/2};}", key)
    if not pos:
        return False
    touch = tab.evaluate("() => 'ontouchstart' in document.documentElement")
    if touch:
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": pos["x"], "y": pos["y"], "id": 1, "radiusX": 12, "radiusY": 12}]})
        time.sleep(0.12)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    else:
        tab.mouse.move(pos["x"] - 15, pos["y"] - 8, steps=6)
        time.sleep(0.25)
        tab.mouse.click(pos["x"], pos["y"])
    return True


def widget_status(tab, key: str) -> str:
    return tab.evaluate("(k)=>{const e=document.getElementById(k); return e?(e.innerText||'').trim():'';}", key)


def _widget_still_idle(tab, key: str) -> bool:
    """True nếu widget vẫn chỉ hiện nút mời bấm, chưa sang đếm ngược."""
    s = widget_status(tab, key)
    return "LẤY MÃ" in s.upper() and _countdown_secs(s) < 0


def click_widget_retry(tab, cdp, key: str, tries: int = 4) -> bool:
    """Bấm nút LẤY MÃ và xác nhận quest đã chạy.

    Trang sponsor thường chặn click (overlay, lazy-load, cần scroll thật).
    Bấm lại với 4 chiến lược khác nhau cho tới khi widget sang đếm ngược.
    """
    for attempt in range(1, tries + 1):
        if not press_widget(tab, cdp, key):
            return False
        if not _widget_still_idle(tab, key):
            return True
        # 2: click thẳng bằng JS vào element/button.
        if attempt == 2:
            tab.evaluate(
                "(k)=>{const e=document.getElementById(k); if(!e) return;"
                "const b=e.querySelector('button')||e; b.click();}", key)
        # 3: focus + Enter (một số widget nghe bàn phím).
        elif attempt == 3:
            tab.evaluate(
                "(k)=>{const e=document.getElementById(k); if(!e) return;"
                "const b=e.querySelector('button')||e; b.focus();}", key)
            tab.keyboard.press("Enter")
        # 4: scroll thật rồi bấm lại.
        elif attempt >= 4:
            for _ in range(3):
                tab.mouse.wheel(0, 120)
                time.sleep(0.4)
            tab.mouse.wheel(0, -120)
            time.sleep(0.4)
        time.sleep(2.0)
        if not _widget_still_idle(tab, key):
            return True
    return False


COUNTDOWN_RE = re.compile(r"(\d+)\s*s")


def _countdown_secs(text: str) -> int:
    """Số giây còn lại trên widget, -1 nếu không đọc được."""
    m = COUNTDOWN_RE.search(text or "")
    return int(m.group(1)) if m else -1


def wait_status(tab, key: str, limit: int) -> str:
    """Chờ widget xong đếm ngược rồi trả mã.

    ``limit`` là số vòng (1.1s/vòng) — giữ tương thích cũ. Nhưng nếu widget
    báo countdown dài hơn (thấy 110s, 119s...), vòng lặp tự nới tới
    ``limit + countdown + 30`` để không cắt ngang. Trước đây cắt ở 93s
    khiến mọi sponsor 120s đều trả "KHÔNG LẤY ĐƯỢC".
    """
    hard_cap = limit + 200
    i = 0
    while i < hard_cap:
        time.sleep(1.1)
        tab.mouse.wheel(0, -70 if i % 2 else 70)
        s = widget_status(tab, key)
        if i % 8 == 0:
            log(f"  t={i * 1.1:.0f}s | {s.replace(chr(10), ' / ')[:70]}")
        if "Mã KM" in s:
            m = CODE_RE.search(s)
            if m:
                return m.group(1)
            return s.split("Mã KM:")[-1].strip().split()[0]
        # Bước 2 đánh dấu bằng link/step mới; "link" trần tránh khớp nhầm.
        low = s.lower()
        if "link" in low or "bước 2" in low or "step 2" in low:
            return "__STEP2__"
        # Nới hạn khi countdown còn dài hơn số vòng còn lại.
        left = _countdown_secs(s)
        if left > 0 and i + left + 30 > hard_cap:
            hard_cap = i + left + 30
        i += 1
    return ""


def run_quest(tab, cdp, key: str) -> str:
    """Quest what-on: 60s (1/2) -> reload -> 15s (2/2) -> mã."""
    # xoá quest cũ trong localStorage, nếu không widget tự ẩn (check_ref=false)
    cleared = tab.evaluate("""() => { const out=[]; for (let i=localStorage.length-1;i>=0;i--){
        const k=localStorage.key(i); if(/_quest$/.test(k)){ out.push(k); localStorage.removeItem(k); } } return out; }""")
    if cleared:
        log("[quest] xoá quest cũ:", cleared)
        tab.reload(wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)
    for _ in range(8):
        tab.mouse.wheel(0, 400)
        time.sleep(0.3)
    if not click_widget_retry(tab, cdp, key):
        log("[quest] không thấy nút LẤY MÃ")
        return ""
    log("[quest] đã bấm nút")
    r = wait_status(tab, key, 85)
    if not r:
        return ""
    if r != "__STEP2__":
        return r
    log("[quest] xong 1/2 -> reload sang 2/2")
    tab.reload(wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    for _ in range(8):
        tab.mouse.wheel(0, 400)
        time.sleep(0.3)
    if not click_widget_retry(tab, cdp, key):
        return ""
    return wait_status(tab, key, 55)


def pick_widget_key(tab, fallback: str) -> str:
    """Trang có thể nhúng nhiều widget; chỉ key nào có nút LẤY MÃ mới là quest."""
    keys = tab.evaluate("""() => [...document.querySelectorAll('script[src*="/widget/service"]')]
        .map(s => (s.src.match(/key=([A-Za-z0-9]+)/) || [])[1]).filter(Boolean)""")
    keys = list(dict.fromkeys((keys or []) + [fallback]))
    for k in keys:
        ok = tab.evaluate(
            "(k)=>{const e=document.getElementById(k); if(!e) return false;"
            "return !!(e.querySelector('button') || /LẤY MÃ/i.test(e.innerText||''));}", k)
        if ok:
            if k != fallback:
                log("[widget] đổi key", fallback, "->", k)
            return k
    return ""


# ------------------------------------------------------------------ main flow
CF_HOST = "challenges.cloudflare.com"


def pass_cloudflare(pg, limit: int = 90) -> bool:
    """Vượt màn 'Just a moment...' của Cloudflare: bấm ô Turnstile.

    Widget Turnstile nằm trong iframe thuộc challenges.cloudflare.com; nếu bấm
    theo frame không ăn thì bấm thẳng vào toạ độ ô checkbox (chỉ khi tiêu đề
    trang vẫn là màn chặn).
    """
    def blocked() -> bool:
        try:
            return "just a moment" in (pg.title() or "").lower()
        except Exception:
            return False

    if not blocked():
        return True
    # toạ độ ô "Verify you are human" theo khung nhìn 1100x900 / 1280x1000
    vp = pg.viewport_size or {"width": 1280, "height": 1000}
    cx, cy = int(vp["width"] * 0.111), int(vp["height"] * 0.373)
    t0 = time.time()
    while time.time() - t0 < limit:
        for f in pg.frames:
            if CF_HOST not in (f.url or ""):
                continue
            for sel in ("input[type=checkbox]", "label", "#challenge-stage"):
                try:
                    f.locator(sel).first.click(timeout=3000)
                    break
                except Exception:
                    continue
        if blocked():
            try:
                pg.mouse.click(cx, cy)
            except Exception:
                pass
        time.sleep(3)
        if not blocked():
            log("[cf] qua Cloudflare sau", int(time.time() - t0), "s")
            return True
    log("[cf] Cloudflare không nhả sau", limit, "s")
    return False


class Engine:
    def __init__(self, alias: str, keep_open: bool = False):
        self.alias = alias
        self.keep_open = keep_open
        self.resp: list[str] = []
        self.page = None
        self.ctx = None

    # -- bước 1: mở link4m, đọc campaign + ảnh hướng dẫn
    def open_link4m(self):
        try:
            from patchright.sync_api import sync_playwright  # bản vá leak CDP
        except ImportError:
            from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        b = self._pw.chromium.connect_over_cdp(CDP)
        self.ctx = b.contexts[0]
        # tạo tab mới TRƯỚC khi đóng tab khác (đóng tab cuối sẽ giết Chrome)
        self.page = self.ctx.new_page()
        for pg in list(self.ctx.pages):
            if pg is not self.page:
                try:
                    pg.close()
                except Exception:
                    pass
        self.page.set_viewport_size({"width": 1280, "height": 1000})
        self._block_heavy_assets()
        self.page.on("response", self._on_resp)
        url = f"https://link4m.net/go/{self.alias}"
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if not pass_cloudflare(self.page):
            raise RuntimeError("Cloudflare chặn (Just a moment) — chưa vượt được")
        time.sleep(7)
        info = self.page.evaluate("""() => {
          const f = document.getElementById('main-form') || document.getElementById('main-form-2');
          const o = {}; if (f) for (const i of f.querySelectorAll('input')) o[i.name] = i.value;
          const w = document.getElementById('captcha-html-wrapper');
          return {form: o, code: w ? w.getAttribute('data-code') : null,
                  imgs: [...document.images].map(i => i.src).filter(s => s.includes('img.link4m.net')),
                  text: (document.body.innerText || '').slice(0, 8000),
                  title: document.title};
        }""")
        if not info["form"]:
            raise RuntimeError("Không thấy form nhập mã — link hỏng hoặc đã bị đổi giao diện")
        log("[link4m]", info["title"][:60])
        log("[campaign]", info["form"].get("campaign_id"), "| display",
            (info["form"].get("display_id") or "")[:12], "| ảnh", len(info["imgs"]))
        return info

    def _on_resp(self, r):
        if "link-info" in r.url:
            try:
                self.resp.append(r.text()[:400])
            except Exception:
                pass

    # Video quảng cáo và font là thứ ngốn RAM nhất trên trang sponsor; box 3.5GB
    # từng chết Chrome ("Connection closed while reading from the driver") giữa
    # vòng đếm 60s. Route chỉ đăng ký cho đúng đuôi file nên request khác không
    # đi qua driver. Ảnh KHÔNG bị chặn: lưới captcha và widget cần ảnh.
    _HEAVY_GLOBS = (
        "**/*.{mp4,webm,m3u8,flv,ts,m4v}",
        "**/*.{woff,woff2,ttf,otf,eot}",
    )

    def _block_heavy_assets(self):
        if self.ctx is None:
            return
        for pattern in self._HEAVY_GLOBS:
            try:
                self.ctx.route(pattern, lambda route: route.abort())
            except Exception as exc:
                log("[ctx] không đặt được route chặn media:", str(exc)[:70])

    # -- bước 2: đọc sponsor (chữ hoặc ảnh) -> xác minh widget
    def google_candidates(self, keyword: str, mask: str) -> list[str]:
        """Tra Google bằng từ khoá trong hướng dẫn, trả link kết quả khớp mask."""
        if not keyword:
            return []
        import urllib.parse as up
        tab = None
        try:
            tab = self.ctx.new_page()
            tab.set_viewport_size({"width": 390, "height": 844})
            q = up.quote(keyword)
            tab.goto(f"https://www.google.com/search?q={q}&hl=vi&num=10",
                     wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)
            links = tab.evaluate(
                "() => [...document.querySelectorAll('a')].map(a => a.href)"
                ".filter(h => h.startsWith('http'))")
        except Exception as exc:
            log("[google] lỗi tìm kiếm:", str(exc)[:80])
            links = []
        finally:
            if tab is not None:
                try:
                    tab.close()
                except Exception:
                    pass
        skip = ("google.", "gstatic.", "youtube.", "facebook.", "instagram.",
                "tiktok.", "support.google", "accounts.google", "policies.google")
        stem = mask.split(".")[0] if mask else ""
        stem2 = ""
        if mask and "*" in mask:
            lab = [x for x in mask.split(".") if "*" in x]
            if lab:
                stem2 = lab[0].replace("*", "")
        out: list[str] = []
        for href in links or []:
            try:
                host = (up.urlparse(href).hostname or "").lower()
            except Exception:
                continue
            if not host or any(s in host for s in skip):
                continue
            if stem2 and stem2.lower() in host:
                out.append(href)
            elif stem and host.split(".")[0] == stem:
                out.append(href)
        log("[google]", keyword, "->", out[:3])
        return out[:6]

    def detect_sponsor(self, info: dict) -> list[tuple[str, str]]:
        import urllib.request
        imgs = info.get("imgs") or []
        text = info.get("text") or ""
        kw, mask = instruction_hints(text)
        if kw or mask:
            log("[hướng dẫn]", "từ khoá:", kw or "-", "| domain che:", mask or "-")
        cands: list[str] = []
        for i, src in enumerate(imgs[:4]):
            pth = f"/tmp/l4m_instr_{i}.jpg"
            try:
                req = urllib.request.Request(src, headers={"User-Agent": UA_DESKTOP})
                data = urllib.request.urlopen(req, timeout=20).read()
                open(pth, "wb").write(data)
            except Exception as exc:
                log("[ocr] tải ảnh lỗi:", str(exc)[:60])
                continue
            try:
                from PIL import Image
                im = Image.open(pth)
                w, h = im.size
                if w < 1000:
                    im.resize((w * 2, h * 2), Image.LANCZOS).convert("RGB").save(pth)
                lines = ocr_lines(pth)
            except Exception as exc:
                log("[ocr] lỗi:", str(exc)[:60])
                continue
            log(f"[ocr {i}]", " | ".join(lines[:3])[:150])
            cands += sponsor_candidates(lines)
        # domain đoán từ mask + kết quả Google theo từ khoá (hướng dẫn dạng chữ)
        guessed = masked_domain_guesses(mask)
        if guessed:
            log("[domain đoán]", guessed[:6])
            cands.extend(f"https://{d}" for d in guessed)
        cands.extend(self.google_candidates(kw, mask))
        # bỏ trùng, giữ thứ tự
        seen, uniq = set(), []
        for u in cands:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        log("[sponsor ứng viên]", uniq[:6])
        found: list[tuple[str, str]] = []
        checked = 0
        for url in uniq + [u for u in cached_sponsors() if u not in uniq]:
            if checked >= 10 or len(found) >= 3:
                break
            checked += 1
            html = fetch_html(url)
            if not html:
                log("[fetch]", url, "-> 0")
                continue
            keys = widget_keys(html)
            log("[fetch]", url, "->", len(html), "bytes,", len(keys), "widget")
            if keys:
                log("[sponsor chọn]", url, "| widget", keys)
                for k in keys:
                    cache_sponsor(url, k)
                    found.append((url, k))
        return found

    # -- bước 3: quest trên trang sponsor
    def harvest_code(self, sponsor: str, key: str) -> str:
        tab = self.ctx.new_page()
        tab.set_viewport_size({"width": 390, "height": 844})
        cdp = self.ctx.new_cdp_session(tab)
        cdp.send("Network.setUserAgentOverride", {"userAgent": UA_MOBILE, "platform": "Linux armv8l"})
        cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
        dom = sponsor.split("//")[1].split("/")[0]
        google = f"https://www.google.com/search?q={dom}&hl=vi"
        tab.goto(sponsor, wait_until="domcontentloaded", timeout=60000, referer=google)
        time.sleep(9)
        log("[sponsor] mở", tab.url[:70], "| ref", tab.evaluate("() => document.referrer")[:40])
        real_key = pick_widget_key(tab, key)
        if not real_key:
            log("[sponsor] không có nút LẤY MÃ trên trang này")
            if not self.keep_open:
                try:
                    tab.close()
                except Exception:
                    pass
            return ""
        code = run_quest(tab, cdp, real_key)
        if not self.keep_open:
            try:
                tab.close()
            except Exception:
                pass
        else:
            tab.bring_to_front()
        return code

    # -- bước 4: điền mã + captcha + đọc link đích (KHÔNG reload trang)
    def _password_input(self):
        """Ô mã đổi id theo campaign (#main-form, -2, -3...), nên dò rộng."""
        a = self.page
        selectors = (
            "#main-form input[name=password]",
            "#main-form-2 input[name=password]",
            "#main-form-3 input[name=password]",
            "form input[name=password]",
            "input[name=password]",
        )
        for sel in selectors:
            loc = a.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=6000)
                return loc
            except Exception:
                continue
        return None

    def _captcha_step(self) -> bool:
        """Trang đã sang bước captcha (phiên trước đã nhập mã) hay chưa."""
        try:
            self.page.locator("#captcha-html-wrapper").first.wait_for(
                state="visible", timeout=3000)
            return True
        except Exception:
            return False

    def _fill_code(self, inp, code: str) -> None:
        inp.click()
        time.sleep(0.3)
        inp.fill("")
        inp.type(code, delay=90)
        try:
            inp.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles: true}));"
                         " el.dispatchEvent(new Event('change', {bubbles: true})); }")
        except Exception:
            pass
        time.sleep(1.2)
        log("[form] mã đã điền:", inp.input_value())

    def submit(self, code: str) -> str:
        a = self.page
        a.bring_to_front()
        time.sleep(1)
        inp = self._password_input()
        captcha_step = False
        if inp is None:
            captcha_step = self._captcha_step()
            log("[form] không thấy ô mã |", a.url[:90], "| bước captcha:", captcha_step)
            if not captcha_step:
                try:
                    log("[form] title:", (a.title() or "")[:80])
                    a.screenshot(path=os.path.join(LOG_DIR, "form_missing.png"), full_page=False)
                except Exception:
                    pass
                # Trang có thể đã tự về bước đầu: reload một lần rồi dò lại.
                try:
                    a.reload(wait_until="domcontentloaded", timeout=45000)
                    time.sleep(4)
                    inp = self._password_input()
                    captcha_step = inp is None and self._captcha_step()
                except Exception as exc:
                    log("[form] reload lỗi:", str(exc)[:90])
        if inp is None and not captcha_step:
            log("[form] bỏ lượt: form mã không tồn tại")
            return ""
        if inp is not None:
            self._fill_code(inp, code)
        else:
            log("[form] vào thẳng bước captcha (mã đã nhập ở phiên trước)")
        a.evaluate("window.scrollTo(0,0)")
        time.sleep(0.8)
        if not click_anchor(a):
            log("[captcha] không thấy checkbox")
            return ""
        deadline = time.time() + 330
        tok = ""
        rounds = 0
        attempts = 0
        while time.time() < deadline and not tok:
            attempts += 1
            self._assert_cdp()
            if attempts > 1:
                # Thử thách hỏng (audio bị chặn): mở lại link để lấy anchor mới.
                # Điểm reCAPTCHA đổi theo phiên, phần lớn lượt sau qua luôn.
                try:
                    a.reload(wait_until="domcontentloaded", timeout=45000)
                    time.sleep(4)
                    inp2 = self._password_input()
                    if inp2 is not None:
                        self._fill_code(inp2, code)
                except Exception as exc:
                    log("[captcha] reload lỗi:", str(exc)[:80])
            if not click_anchor(a):
                log("[captcha] không thấy checkbox")
                continue
            rounds = 0
            while time.time() < deadline:
                time.sleep(1)
                tok = token_now(a)
                if tok:
                    break
                if find_challenge(a):
                    rounds += 1
                    log(f"[captcha] thử thách vòng {rounds}")
                    tok = solve_challenge(a)
                    if tok:
                        break
                    if rounds >= 2:
                        break
                    for f in a.frames:
                        if "bframe" in (f.url or ""):
                            try:
                                f.locator("#recaptcha-reload-button").first.click(timeout=3000)
                            except Exception:
                                pass
                    time.sleep(2)
            if not tok:
                log(f"[captcha] lần {attempts} thua — mở lại trang")
        log("[captcha] token", len(tok))
        if not tok:
            return ""
        href = ""
        for _ in range(25):
            href = a.evaluate("""() => { const b=document.querySelector('.get-link');
                return b ? (b.getAttribute('href') || '') : ''; }""")
            if href and href.startswith("http"):
                break
            time.sleep(1)
        if not href:
            # Nút "Click vào đây để tiếp tục" chỉ bấm được khi đã hết disabled.
            try:
                btn = a.locator(".get-link").first
                cls = (btn.get_attribute("class") or "")
                if btn.is_visible() and "disabled" not in cls:
                    log("[form] bấm nút tiếp tục")
                    btn.click()
                    time.sleep(4)
                    href = a.evaluate("""() => { const b=document.querySelector('.get-link');
                        return b ? (b.getAttribute('href') || '') : ''; }""")
            except Exception as exc:
                log("[form] nút tiếp tục lỗi:", str(exc)[:90])
        log("[server]", self.resp[-1][:220] if self.resp else "không bắt được response")
        return href

    # -- chạy trọn gói, thử lần lượt các sponsor ứng viên
    _DROPPED = ("connection closed", "target closed", "browser has been closed",
                "browser closed", "has been closed")

    def _reset_connection(self):
        """Chrome chết/ngắt CDP giữa flow: buông phiên cũ rồi dựng lại."""
        log("[engine] mất kết nối Chrome — dựng lại phiên và chạy lại một lần")
        try:
            self._pw.stop()
        except Exception:
            pass
        self.page = None
        self.ctx = None
        if not _cdp_up():
            # ensure_chrome() thấy port chết thì launch mới; gọi _kill_chrome()
            # trước để dọn xác process còn giữ profile.
            _kill_chrome()
        ensure_chrome()

    def _assert_cdp(self):
        """Chrome chết thì ném lỗi khớp `_DROPPED` để run() dựng lại phiên."""
        if not _cdp_up():
            raise RuntimeError("browser has been closed: Chrome CDP không phản hồi")

    def run(self) -> dict:
        try:
            return self._run_once()
        except Exception as exc:
            if not self._is_dropped(exc):
                raise
            self._reset_connection()
            return self._run_once()

    def _is_dropped(self, exc: BaseException) -> bool:
        text = str(exc).lower()
        return any(marker in text for marker in self._DROPPED)

    def _run_once(self) -> dict:
        info = self.open_link4m()
        if self._captcha_step():
            # Phiên trước đã nhập mã cho alias này: link4m giữ trạng thái và chỉ
            # còn captcha. Bỏ 4 phút quest, vào thẳng bước cuối.
            log("[flow] trang đã ở bước captcha — bỏ qua quest")
            href = self.submit("")
            if href:
                save_destination(href)
                return {"ok": True, "alias": self.alias, "code": "",
                        "sponsor": "", "destination": href,
                        "server": self.resp[-1] if self.resp else ""}
        sponsors = self.detect_sponsor(info)
        if not sponsors:
            return {"ok": False, "stage": "sponsor", "imgs": info["imgs"]}
        last_code = ""
        for i, (sponsor, key) in enumerate(sponsors[:3]):
            log(f"[thử {i + 1}/{min(3, len(sponsors))}]", sponsor)
            try:
                code = self.harvest_code(sponsor, key)
            except Exception as exc:
                if self._is_dropped(exc):
                    raise
                log("[quest] lỗi:", str(exc)[:120])
                code = ""
            log("[quest] mã:", code or "KHÔNG LẤY ĐƯỢC")
            if not code:
                continue
            last_code = code
            try:
                href = self.submit(code)
            except Exception as exc:
                if self._is_dropped(exc):
                    raise
                log("[submit] lỗi:", str(exc)[:120])
                href = ""
            if href:
                save_destination(href)
                return {"ok": True, "alias": self.alias, "code": code,
                        "sponsor": sponsor, "destination": href,
                        "server": self.resp[-1] if self.resp else ""}
            log("[submit] thất bại -> thử sponsor khác")
        return {"ok": False, "stage": "submit", "code": last_code,
                "server": self.resp[-1] if self.resp else ""}

    def close(self):
        try:
            self._pw.stop()
        except Exception:
            pass


def bypass_alias(alias: str, keep_open: bool = False) -> dict:
    """API lập trình: chạy trọn flow cho một alias và trả dict kết quả.

    Dùng cho service (không in log CLI, không đụng argv).
    """
    ensure_chrome()
    eng = Engine(alias, keep_open=keep_open)
    try:
        return eng.run()
    finally:
        eng.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Link4M bypass — OCR sponsor, quest, captcha, link đích")
    ap.add_argument("alias", nargs="?", default="2kCcIqn", help="mã link /go/<alias>")
    ap.add_argument("--json", action="store_true", help="chỉ in JSON kết quả")
    ap.add_argument("--keep-open", action="store_true", help="giữ tab sponsor sau khi lấy mã")
    args = ap.parse_args(argv)

    ensure_chrome()
    eng = Engine(args.alias, keep_open=args.keep_open)
    try:
        res = eng.run()
    finally:
        eng.close()
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print()
        log("=== KẾT QUẢ ===")
        for k in ("ok", "code", "sponsor", "destination", "stage", "server"):
            if k in res:
                log(f"{k:12}: {res[k]}")
    save_result(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
