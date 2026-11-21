import requests
import re
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
alias = '68pw167Y'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
}

# Step 1: GET page
r = session.get(f'https://link4m.net/go/{alias}', headers=headers)
print('GET page status:', r.status_code)
print('Cookies after GET:', session.cookies.get_dict())

m = re.search(r'data-code\s*=\s*[\"\']([a-f0-9]+)[\"\']', r.text)
if not m:
    print('data-code not found')
    exit()

data_code = m.group(1)
print('Fresh data-code:', data_code[:30], '...')

# Step 2: POST get-advertise
api_headers = {
    'User-Agent': headers['User-Agent'],
    'Origin': 'https://link4m.net',
    'Referer': f'https://link4m.net/go/{alias}',
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

adv_res = session.post(
    'https://s1.link4m.app/api/campaign/get-advertise',
    headers=api_headers,
    data={'alias': alias, 'codes': data_code}
)
print('POST adv status:', adv_res.status_code)
print('Cookies after POST:', session.cookies.get_dict())
res = adv_res.json()
print('Success:', res.get('success'))
if res.get('success'):
    print('Campaign ID:', res.get('data', {}).get('campaign_id'))
    print('Display ID:', res.get('data', {}).get('display_id'))
    print('Prefix:', res.get('data', {}).get('prefix'))
    with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_adv.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
else:
    print('Full Response:', res)
