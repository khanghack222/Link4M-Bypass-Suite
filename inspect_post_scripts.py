import requests
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

r = requests.get('https://khovatlieunoithatdanang.com/van-ep-phu-phim-da-nang', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', r.text)
for s in scripts:
    print('Script:', s)

# Also check for inline scripts
inline = re.findall(r'<script.*?>([\s\S]*?)</script>', r.text)
print('Total inline scripts:', len(inline))
for i, s in enumerate(inline):
    if any(k in s.lower() for k in ['campaign', 'display', 'link4m', 'l4m', 'traffic', 'button']):
        print(f'Inline #{i}:', s[:300])
