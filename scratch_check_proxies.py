import sys, os, requests
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'c:\Users\XUAN\.gemini\antigravity\scratch\Link4M_Bypass_Suite\src\core')
from config import load_proxies

proxies = load_proxies()
print(f"Checking {len(proxies)} proxies...", flush=True)

live_proxy = None
for p in proxies:
    srv = p['server']
    host = srv.replace('http://', '')
    prx = {
        'http': f"http://{p['username']}:{p['password']}@{host}",
        'https': f"http://{p['username']}:{p['password']}@{host}"
    }
    try:
        r = requests.get('https://api.ipify.org?format=json', proxies=prx, timeout=3)
        if r.status_code == 200:
            ip = r.json().get('ip')
            print(f"  [ALIVE] {srv} -> Exit IP: {ip}", flush=True)
            live_proxy = p
            break
    except Exception as e:
        print(f"  [FAIL] {srv}", flush=True)

if live_proxy:
    import json
    with open('live_proxy.json', 'w', encoding='utf-8') as f:
        json.dump(live_proxy, f)
    print("Saved live proxy to live_proxy.json!", flush=True)
else:
    print("No authenticated proxy responded. Checking open proxies...", flush=True)
