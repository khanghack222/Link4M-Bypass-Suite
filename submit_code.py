import requests
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
alias = '68pw167Y'
code = 'LbxReE'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Origin': 'https://link4m.net',
    'Referer': f'https://link4m.net/go/{alias}',
    'X-Requested-With': 'XMLHttpRequest'
}

# Fetch form fields from fresh_adv.json
with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_adv.json', 'r', encoding='utf-8') as f:
    adv = json.load(f)

# Extract campaign_id, display_id, prefix from form
import re
form_html = adv.get('form', '')
cid = re.search(r'name=["\']campaign_id["\']\s+value=["\']([^"\']+)["\']', form_html).group(1)
did = re.search(r'name=["\']display_id["\']\s+value=["\']([^"\']+)["\']', form_html).group(1)
prefix = re.search(r'name=["\']prefix["\']\s+value=["\']([^"\']+)["\']', form_html).group(1)

print('Alias:', alias)
print('Campaign ID:', cid)
print('Display ID:', did)
print('Prefix:', prefix)
print('Code:', code)

payload = {
    'password': code,
    'alias': alias,
    'campaign_id': cid,
    'display_id': did,
    'prefix': prefix
}

r = session.post(
    'https://s1.link4m.app/links/get-link-info',
    headers=headers,
    data=payload
)

print('Status:', r.status_code)
print('Response text:', r.text)
try:
    print('JSON response:', r.json())
except Exception as e:
    print('Failed to parse json:', e)
