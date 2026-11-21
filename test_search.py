import requests
import re
import sys
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

query = "789club"
# Search via DuckDuckGo Lite
url = f"https://lite.duckduckgo.com/lite/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded'
}

r = requests.post(url, headers=headers, data={'q': query})
links = re.findall(r'href=["\'](https?://[^"\']+)["\']', r.text)

print(f"Results for '{query}':")
filtered = []
for l in links:
    if 'duckduckgo' not in l and ('789' in l or '.cc' in l):
        filtered.append(l)

for f in set(filtered):
    print(" -", f)
