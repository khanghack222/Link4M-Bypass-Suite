import sys
import os
import urllib.request
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Danh sách API trả về proxy tươi mới nhất theo thời gian thực (real-time)
JIT_SOURCES = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/VN/data.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=all&country=VN&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"
]

def fetch_fresh_candidates(limit=60):
    candidates = []
    for src in JIT_SOURCES:
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                lines = resp.read().decode("utf-8", errors="ignore").splitlines()
                for l in lines:
                    l = l.strip()
                    if l and not l.startswith("#") and ":" in l:
                        candidates.append(l)
                        if len(candidates) >= limit:
                            return candidates
        except Exception:
            continue
    return candidates

def test_single_proxy(proxy_str, timeout=1.5):
    proto = "http"
    addr = proxy_str
    if "://" in proxy_str:
        proto, addr = proxy_str.split("://", 1)
        proto = proto.lower()

    if ":" not in addr:
        return None

    try:
        ip, port_s = addr.split(":")[:2]
        port = int(port_s)
    except Exception:
        return None

    t0 = time.perf_counter()
    # 1. Test TCP socket handshake
    try:
        s = socket.socket()
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
    except Exception:
        return None

    # 2. Test thực tế gửi HTTP GET qua proxy để đảm bảo không bị ERR_EMPTY_RESPONSE hoặc CERT_INVALID
    formatted = f"{proto}://{ip}:{port}"
    try:
        import urllib.request
        proxies = {"http": formatted, "https": formatted}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
        # Test trực tiếp bằng httpbin / ipify với timeout ngắn
        req = urllib.request.Request("http://httpbin.org/ip", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
    except Exception:
        return None

    latency = round((time.perf_counter() - t0) * 1000)
    return {
        "server": formatted,
        "protocol": proto,
        "raw": proxy_str,
        "latency_ms": latency
    }

def get_live_proxy_jit(timeout_budget=3.0):
    """
    CÀO VÀ DÙNG NGAY LẬP TỨC TRONG 2 GIÂY.
    Không tích trữ file, không lưu trữ quá hạn.
    """
    candidates = fetch_fresh_candidates(limit=40)
    print(f"[*] [JIT Proxy] Cào nhanh {len(candidates)} ứng viên mới nhất, đang test song song...", flush=True)

    with ThreadPoolExecutor(max_workers=40) as ex:
        futures = [ex.submit(test_single_proxy, c) for c in candidates]
        for f in as_completed(futures):
            res = f.result()
            if res:
                print(f"[+] [JIT Proxy] Tìm thấy proxy SỐNG TẠI THỜI ĐIỂM NÀY: {res['server']} (Ping: {res['latency_ms']}ms)", flush=True)
                return res
    return None

if __name__ == "__main__":
    t0 = time.time()
    live = get_live_proxy_jit()
    elapsed = round(time.time() - t0, 2)
    print(f"Kết quả JIT: {live} (Lấy và test xong trong {elapsed}s)")
