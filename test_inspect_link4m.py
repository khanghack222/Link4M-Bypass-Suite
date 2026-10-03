import urllib.request, re

req = urllib.request.Request(
    'https://link4m.net/go/2kCcIqn',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
)
with urllib.request.urlopen(req) as r:
    html = r.read().decode('utf-8', errors='ignore')

scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html)
for s in scripts:
    print('Script:', s)

inlines = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for inc in inlines:
    if any(k in inc for k in ['checkPassword', 'campaign', 'main-form', 'prefix', 'alias']):
        print('Inline match:\n', inc[:800])
