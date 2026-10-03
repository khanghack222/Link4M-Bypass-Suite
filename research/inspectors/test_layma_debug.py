import requests, sys, re

sys.stdout.reconfigure(encoding='utf-8')
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
r = requests.get('https://layma.net/Kd1onyItr', headers=headers)
html = r.text

print("=== LAYMA HTML INSPECTION ===")
for el_id in ['tokenId', 'campainId', 'TK1', 'linkWeb', 'linkNoidung', 'keyToken']:
    m = re.search(r'id=[\"\']' + el_id + r'[\"\'][^>]*>(.*?)</', html, re.DOTALL)
    print(f"{el_id}:", m.group(1).strip() if m else "NOT FOUND")

# Check visitor API call
v_info = {
    "browser": "Chrome",
    "browserVersion": "122.0.0.0",
    "browserMajorVersion": 122,
    "cookies": True,
    "mobile": False,
    "os": "Windows 10",
    "osVersion": "10",
    "screen": "1366 x 768",
    "token": "Kd1onyItr"
}
r_vis = requests.post('https://api.layma.net/api/traffic/visitor', json=v_info, headers={**headers, 'Referer': 'https://layma.net/Kd1onyItr'})
print("visitor status:", r_vis.status_code, "visitor resp:", r_vis.text)
