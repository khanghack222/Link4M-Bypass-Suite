import os
import sys
import time
import json
import urllib.parse
from playwright.sync_api import sync_playwright

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(ROOT_DIR, "src", "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import bypass
from config import CHROME_PATH

TOKEN = "6a959a071ed1793bdc635c17"
OUTPUT_REPORT = os.path.join(ROOT_DIR, "benchmark_100_links.json")
LOG_BENCHMARK = os.path.join(ROOT_DIR, "benchmark_100_links.log")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def log_bench(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_BENCHMARK, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def generate_links(count=100):
    log_bench(f"[*] Bat dau tao {count} link test qua Link4M API...")
    links = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for i in range(1, count + 1):
            raw_dest = f"https://httpbin.org/get?test_id={i}&ts={int(time.time()*1000)}"
            api_url = f"https://link4m.co/api-shorten/v2?api={TOKEN}&url={urllib.parse.quote(raw_dest)}"
            try:
                page.goto(api_url, timeout=15000)
                pre_elem = page.locator("pre")
                content = pre_elem.inner_text().strip() if pre_elem.count() > 0 else page.locator("body").inner_text().strip()
                data = json.loads(content)
                if data.get("status") == "success" and data.get("shortenedUrl"):
                    short_url = data.get("shortenedUrl")
                    links.append({"id": i, "target": raw_dest, "short_url": short_url})
                    if i % 10 == 0 or i == count:
                        log_bench(f"  [+] Da tao {i}/{count} link: {short_url}")
                else:
                    log_bench(f"  [-] Loi tao link {i}: {data}")
            except Exception as e:
                log_bench(f"  [-] Exception tao link {i}: {e}")
            time.sleep(0.3)
        browser.close()
    return links

def run_benchmark(total=100):
    if os.path.exists(LOG_BENCHMARK):
        os.remove(LOG_BENCHMARK)
        
    links = generate_links(total)
    log_bench(f"\n[*] Tong so link da tao thanh cong: {len(links)}/{total}")
    
    results = []
    success_count = 0
    fail_count = 0
    
    start_total_time = time.time()
    
    for idx, item in enumerate(links, 1):
        s_url = item["short_url"]
        expected = item["target"]
        log_bench(f"\n=======================================================")
        log_bench(f"🚀 [TEST {idx}/{len(links)}] Bat dau bypass: {s_url}")
        log_bench(f"   Dich ky vong: {expected}")
        log_bench(f"=======================================================")
        
        t0 = time.time()
        # Xoa file ket qua cu
        for p in [os.path.join(ROOT_DIR, "destination_url.txt"), os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt")]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
                
        try:
            bypass.run(target_url=s_url, headless=True)
        except Exception as e:
            log_bench(f"[!] Runner exception: {e}")
            
        elapsed = round(time.time() - t0, 2)
        
        # Doc ket qua
        captured = ""
        for p in [os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), os.path.join(ROOT_DIR, "destination_url.txt")]:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        c = f.read().strip()
                        if c.startswith("http"):
                            captured = c
                            break
                except Exception:
                    pass
                    
        is_ok = (captured == expected) or (expected in captured) or (bool(captured) and "link4m" not in captured)
        if is_ok:
            success_count += 1
            status = "PASS"
            log_bench(f"✔ [PASS] Test {idx} thanh cong ({elapsed}s)! Link thu duoc: {captured}")
        else:
            fail_count += 1
            status = "FAIL"
            log_bench(f"❌ [FAIL] Test {idx} that bai ({elapsed}s)! Thu duoc: '{captured}'")
            
        results.append({
            "id": item["id"],
            "short_url": s_url,
            "expected": expected,
            "captured": captured,
            "status": status,
            "duration_sec": elapsed
        })
        
        # Ghi report tam thoi sau moi luot
        with open(OUTPUT_REPORT, "w", encoding="utf-8") as f_rep:
            json.dump({
                "total_tested": idx,
                "success": success_count,
                "fail": fail_count,
                "success_rate": f"{(success_count/idx)*100:.1f}%",
                "details": results
            }, f_rep, indent=2, ensure_ascii=False)
            
        # Nghi nhe 1s giua cac luot de giam ap luc captcha
        time.sleep(1)

    total_time = round(time.time() - start_total_time, 2)
    log_bench(f"\n=======================================================")
    log_bench(f"🏆 BENCHMARK HOAN TAT!")
    log_bench(f"   Tong so link test: {len(links)}")
    log_bench(f"   Thanh cong: {success_count} ({ (success_count/len(links))*100:.1f}% )")
    log_bench(f"   That bai: {fail_count}")
    log_bench(f"   Tong thoi gian: {total_time}s (TB: {total_time/len(links):.1f}s/link)")
    log_bench(f"=======================================================\n")

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    run_benchmark(count)
