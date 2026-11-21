import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
r = requests.get('https://link4m.net/AVsQ2rd3', headers=headers)
print('Final URL:', r.url)

alias_match = re.search(r"data-alias\s*=\s*'([^']+)'", r.text)
code_match = re.search(r'data-code\s*=\s*"([^"]+)"', r.text)
if alias_match and code_match:
    alias = alias_match.group(1)
    code = code_match.group(1)
    print('Alias:', alias)
    print('Code length:', len(code))

    r_adv = requests.post('https://s1.link4m.app/api/campaign/get-advertise', data={'alias': alias, 'codes': code}, headers=headers)
    d = r_adv.json()
    print('Get-advertise success:', d.get('success'))
    if 'html' in d:
        with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_adv.html', 'w', encoding='utf-8') as f:
            f.write(d['html'])
        print('Saved fresh_adv.html, length:', len(d['html']))
    else:
        print('Keys in response:', list(d.keys()))
        print('Info:', d.get('info'))
