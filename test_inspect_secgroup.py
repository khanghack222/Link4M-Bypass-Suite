import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    'https://secgroup.vn/',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
)
with urllib.request.urlopen(req, context=ctx) as r:
    html = r.read().decode('utf-8', errors='ignore')

scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html)
print('Scripts count:', len(scripts))
for s in scripts:
    if any(k in s for k in ['traffic', 'what', 'code', 'analytic', 'button', 'key', 'layma', 'widget', 'service']):
        print('Traffic script:', s)

keys = re.findall(r'[a-zA-Z0-9_\-]{8,32}', html)
inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print('Inline scripts count:', len(inline_scripts))
for sc in inline_scripts:
    if any(k in sc for k in ['traffic', 'what', 'code', 'countdown', 'layma', 'token', 'link4m']):
        print('Matched inline script snippet:', sc[:400])
