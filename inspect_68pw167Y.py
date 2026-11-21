import requests
import re
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

alias = '68pw167Y'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
}

# 1. Fetch initial page
r = requests.get(f'https://link4m.net/go/{alias}', headers=headers)
print('Status:', r.status_code)
data_code_match = re.search(r'data-code\s*=\s*[\"\']([a-f0-9]+)[\"\']', r.text)
if not data_code_match:
    print('No data-code found')
    exit()

data_code = data_code_match.group(1)
print('data-code:', data_code[:30], '...')

# 2. Get advertise / campaign info
api_headers = headers.copy()
api_headers.update({
    'Origin': 'https://link4m.net',
    'Referer': f'https://link4m.net/go/{alias}',
    'Content-Type': 'application/json',
})

adv_res = requests.post(
    'https://s1.link4m.app/api/campaign/get-advertise',
    headers=api_headers,
    json={'alias': alias, 'codes': data_code}
)
print('Adv status:', adv_res.status_code)
adv_data = adv_res.json()
if adv_data.get('success'):
    c_info = adv_data.get('data', {})
    print('Campaign ID:', c_info.get('campaign_id'))
    print('Display ID:', c_info.get('display_id'))
    print('Prefix:', c_info.get('prefix'))
    html = c_info.get('html', '')
    print('HTML length:', len(html))
    with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/campaign_html.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Saved campaign_html.html')
else:
    print('Adv error:', adv_data)
