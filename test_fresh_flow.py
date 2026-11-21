import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
})

url = "https://link4m.net/go/68pw167Y"
r = s.get(url)
print(f"[1] Page status: {r.status_code}")

m_alias = re.search(r"data-alias\s*=\s*['\"]([^'\"]+)['\"]", r.text)
m_code = re.search(r"data-code\s*=\s*['\"]([^'\"]+)['\"]", r.text)

if not m_alias or not m_code:
    print("[!] Could not parse alias or code from fresh page")
    sys.exit(1)

alias = m_alias.group(1)
code = m_code.group(1)
print(f"[2] Fresh alias: {alias}, code: {code[:30]}...")

post_headers = {
    "User-Agent": s.headers["User-Agent"],
    "Origin": "https://link4m.net",
    "Referer": url,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

resp = s.post(
    "https://s1.link4m.app/api/campaign/get-advertise",
    data={"alias": alias, "codes": code},
    headers=post_headers
)

print(f"[3] get-advertise status: {resp.status_code}")
data = resp.json()
print(f"[4] get-advertise response:\n{data}")
