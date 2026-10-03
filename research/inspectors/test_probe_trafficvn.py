import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import re

url = "http://trafficvn.com/get/MFGm2tAlcSn"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', errors='ignore')
    print("HTML bytes:", len(html))
    scripts = re.findall(r'<script[^>]*src=[\'"]([^\'"]+)[\'"]', html)
    print("Scripts:", scripts)
    inline = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    print("Inline scripts count:", len(inline))
    for s in inline:
        if any(k in s for k in ['camp', 'token', 'check', 'url', 'session']):
            print("\n--- Matching Script Snippet ---")
            for line in s.splitlines():
                if any(k in line for k in ['get_', 'camp', 'token', 'post', 'fetch', 'url']):
                    print(" ", line.strip()[:100])
except Exception as e:
    print("Error:", e)
