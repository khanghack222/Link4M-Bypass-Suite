import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Let's test calling /links/get-link-info with various payloads to reverse-engineer server-side validation
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Origin": "https://link4m.net",
    "Referer": "https://link4m.net/go/68pw167Y",
    "X-Requested-With": "XMLHttpRequest"
})

url = "https://s1.link4m.app/links/get-link-info"

# 1. Empty payload
r1 = session.post(url, data={})
print("Test 1 (Empty):", r1.status_code, r1.text[:200])

# 2. Basic parameters without recaptcha
payload_no_cap = {
    "alias": "68pw167Y",
    "campaign_id": "6ab9cefc52536a76420cee22",
    "display_id": "6ac4fb019565a82e04068c8d",
    "prefix": "d0eb59b7d2eb6df5c2c4af96c332250c",
    "password": "123456"
}
r2 = session.post(url, data=payload_no_cap)
print("Test 2 (No recap):", r2.status_code, r2.text[:200])

# 3. With dummy recaptcha
payload_dummy_cap = dict(payload_no_cap)
payload_dummy_cap["g-recaptcha-response"] = "dummy_token"
r3 = session.post(url, data=payload_dummy_cap)
print("Test 3 (Dummy recap):", r3.status_code, r3.text[:200])
