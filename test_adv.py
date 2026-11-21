import requests
import re
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

alias = '68pw167Y'
with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/page_dump.html', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'data-code\s*=\s*[\"\']([a-f0-9]+)[\"\']', text)
data_code = m.group(1)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Origin': 'https://link4m.net',
    'Referer': f'https://link4m.net/go/{alias}',
    'X-Requested-With': 'XMLHttpRequest'
}

r = requests.post(
    'https://s1.link4m.app/api/campaign/get-advertise',
    headers=headers,
    data={'alias': alias, 'codes': data_code}
)
print('Status:', r.status_code)
res = r.json()
print('Success:', res.get('success'))
if res.get('success'):
    print('Campaign ID:', res.get('data', {}).get('campaign_id'))
    print('Display ID:', res.get('data', {}).get('display_id'))
    print('Prefix:', res.get('data', {}).get('prefix'))
    print('Keys:', list(res.get('data', {}).keys()))
    with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/adv_response.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
else:
    print('Full Response:', res)
