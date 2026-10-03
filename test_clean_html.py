import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scratch_link4m_advertise.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

html = d['data']['html']
clean = re.sub(r'data:image/[^;]+;base64,[a-zA-Z0-9+/=]+', '[B64]', html)
print('HTML structure without b64:')
print(clean)
