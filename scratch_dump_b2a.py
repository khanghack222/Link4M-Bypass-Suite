import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request('https://chyarny.com/vi-vn/', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
    html = resp.read().decode('utf-8', 'ignore')
    inlines = re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>', html, re.DOTALL)
    for s in inlines:
        if 'b2a' in s:
            with open('scratch_b2a.js', 'w', encoding='utf-8') as f:
                f.write(s)
            print("Wrote scratch_b2a.js! Size:", len(s))
            break
