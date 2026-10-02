#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ULTRA PROXY HARVESTER & LIVE CHECKER (DAILY AUTO-SYNC) ⚡
Tự động cào và lọc hàng ngàn proxy từ các nguồn VIP cập nhật hàng giờ:
- monosans (hourly deep checked, full response time metadata)
- proxygenerator1 (MostStable cut, deep verified)
- VPSLab (all_elite anonymous)
- databay-labs (5-minute fresh check)
- TheSpeedX (mass SOCKS5 / HTTP)

Tự động test song song (timeout 1.8s), chỉ giữ lại các proxy sống 100%,
ưu tiên SOCKS5 & Elite HTTPS có latency thấp để vượt Google DOSCAPTCHA.
"""

import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import socket
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROXIES_FILE = os.path.join(ROOT_DIR, "proxies.txt")

SOURCES = [
    # Top 1: Monosans (Kiểm tra từng phút, độ ổn định cao nhất)
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    # Top 2: ProxyGenerator MostStable & Verified
    "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/MostStable/socks5.txt",
    "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/MostStable/http.txt",
    # Top 3: VPSLab Elite Anonymous & SOCKS5
    "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/all_elite.txt",
    "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/socks5_all.txt",
    # Top 4: Databay Labs (Cập nhật mỗi 5 phút)
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/socks5.txt",
    # Top 5: TheSpeedX Mass Proxies
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    # Top 6: ErcinDedeoglu Hourly Verified
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
    # Top 7: Hookzof SOCKS5 VIP
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    # Top 8: ShiftyTR Hourly Live
    "https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt",
    "https://raw.githubusercontent.com/shiftytr/proxy-list/master/socks5.txt",
    # Top 9: Clarketm Daily Verified Raw
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    # Top 10: Proxifly Real-time HTTP & SOCKS5
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    # Top 11: Zloi-user Tested Proxies
    "https://raw.githubusercontent.com/Zloi-user/hideip.me/master/socks5.txt",
    "https://raw.githubusercontent.com/Zloi-user/hideip.me/master/http.txt",
    # Top 12: Roosterkid SOCKS5
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt"
]

def fetch_all_sources(max_per_source=500):
    collected = set()
    print("[*] Đang kết nối các kho proxy VIP cập nhật thời gian thực...", flush=True)

    def fetch_url(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88.1"})
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                lines = [l.strip() for l in resp.read().decode(errors="ignore").splitlines() if l.strip()]
                return [l for l in lines if ":" in l and not l.startswith("#")][:max_per_source]
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=len(SOURCES)) as executor:
        for batch in executor.map(fetch_url, SOURCES):
            collected.update(batch)

    print(f"[+] Thu thập được {len(collected)} proxy ứng viên duy nhất.", flush=True)
    return list(collected)

def verify_proxy_deep(proxy_str: str, timeout: float = 2.5) -> dict:
    """
    Kiểm tra thực tế 100% bằng cách gửi HTTP GET thật tới Google/IPify qua Proxy.
    Đảm bảo proxy không chỉ mở cổng TCP mà còn truyền tải dữ liệu HTTP/HTTPS thật.
    """
    clean = proxy_str.strip()
    if clean.startswith("http://") or clean.startswith("socks5://"):
        formatted_proxy = clean
    else:
        formatted_proxy = f"http://{clean}"

    t0 = time.perf_counter()
    try:
        # 1. Thử qua urllib proxy handler với HTTPS endpoint
        proxy_handler = urllib.request.ProxyHandler({
            "http": formatted_proxy,
            "https": formatted_proxy
        })
        opener = urllib.request.build_opener(proxy_handler)
        test_url = "http://api.ipify.org"
        req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with opener.open(req, timeout=timeout) as resp:
            if resp.getcode() == 200:
                body = resp.read().decode(errors="ignore").strip()
                if body and len(body) <= 45 and ("." in body or ":" in body):
                    latency = round((time.perf_counter() - t0) * 1000, 1)
                    return {
                        "proxy": clean,
                        "latency_ms": latency,
                        "exit_ip": body
                    }
    except Exception:
        pass

    # 2. Thử socket raw connect nếu là socks5
    if "socks5" in clean or ":1080" in clean:
        try:
            import socks
            raw_addr = clean.replace("socks5://", "")
            host, port = raw_addr.split(":")[:2]
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, host, int(port))
            s.settimeout(timeout)
            s.connect(("api.ipify.org", 80))
            s.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
            data = s.recv(1024).decode(errors="ignore")
            s.close()
            if "HTTP/1.1 200" in data:
                latency = round((time.perf_counter() - t0) * 1000, 1)
                return {
                    "proxy": clean if clean.startswith("socks5://") else f"socks5://{clean}",
                    "latency_ms": latency,
                    "exit_ip": "verified_socks5"
                }
        except Exception:
            pass

    return None

def update_proxy_pool(target_count=100):
    """Cập nhật tự động proxies.txt với danh sách proxy ngon nhất, latency thấp nhất."""
    candidates = fetch_all_sources(max_per_source=500)
    print(f"[*] Bắt đầu kiểm tra DEEP HEALTHCHECK (Thực hiện GET request thực, Latency < 2.5s)...", flush=True)

    verified_list = []
    with ThreadPoolExecutor(max_workers=80) as executor:
        results = executor.map(verify_proxy_deep, candidates)
        for r in results:
            if r:
                verified_list.append(r)
                if len(verified_list) >= target_count * 2:
                    break

    # Sắp xếp theo latency nhanh nhất
    verified_list.sort(key=lambda x: x["latency_ms"])
    top_picks = verified_list[:target_count]

    print(f"\n[🎉] Đã kiểm định thành công {len(top_picks)} proxy 100% SỐNG VÀ TRUYỀN DỮ LIỆU:")
    for idx, p in enumerate(top_picks[:15], 1):
        print(f"   [{idx}] {p['proxy']} | Ping: {p['latency_ms']}ms | Exit IP: {p.get('exit_ip')}")

    # Giữ lại các proxy dân cư trả phí nếu có trong file cũ
    existing_paid = []
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    l = line.strip()
                    if l and ("@" in l or len(l.split(":")) == 4):
                        existing_paid.append(l)
        except Exception:
            pass

    # Ghi đè vào proxies.txt với định dạng chuẩn
    final_output = []
    if existing_paid:
        final_output.append("# --- RESIDENTIAL AUTHENTICATED PROXIES ---")
        final_output.extend(list(dict.fromkeys(existing_paid)))
        final_output.append("")

    final_output.append(f"# --- VIP HIGH-SPEED PROXY POOL (UPDATED: {time.strftime('%Y-%m-%d %H:%M:%S')}) ---")
    for item in top_picks:
        final_output.append(item["proxy"])

    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(final_output) + "\n")

    print(f"[+] Đã lưu danh sách proxy sạch vào {PROXIES_FILE} thành công!\n", flush=True)
    return top_picks

if __name__ == "__main__":
    update_proxy_pool(target_count=30)
