import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request, re

url = 'https://bbmkts.com/go/PGzlY'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', errors='ignore')
print("--- ALL SCRIPT CONTENTS WITH DOMAIN/TOKEN/CONFIG ---")
for s in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S):
    if any(k in s for k in ['taskConfig', 'requiredDomains', 'token', 'link', 'ajax', 'domain']):
        for line in s.splitlines():
            l = line.strip()
            if any(k in l for k in ['taskConfig', 'required', 'token', 'link', 'domain', 'url']):
                print("  ", l[:120])
