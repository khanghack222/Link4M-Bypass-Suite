import requests
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Test calling /links/check-captcha with campaign parameters from get-advertise
# Earlier campaign parameters:
# campaign_id = "69bfa54f833ad2e2750df2e2"
# display_id = "6ac62b42d47668e97903ed4e"
# prefix = "2a4b9794f790497d3ca6292915768667"
# alias = "68pw167Y"

url = "https://s1.link4m.app/links/check-captcha"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Origin": "https://link4m.net",
    "Referer": "https://link4m.net/go/68pw167Y",
    "X-Requested-With": "XMLHttpRequest"
}

payload = {
    "alias": "68pw167Y",
    "campaign_id": "69bfa54f833ad2e2750df2e2",
    "display_id": "6ac62b42d47668e97903ed4e",
    "prefix": "2a4b9794f790497d3ca6292915768667"
}

r = requests.post(url, data=payload, headers=headers)
print("Response with campaign data:", r.status_code, r.text)
