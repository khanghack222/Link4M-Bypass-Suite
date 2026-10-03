import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request('https://chyarny.com/vi-vn/', headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
        html = resp.read().decode('utf-8', 'ignore')
        scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html)
        print("Scripts:", scripts)
        for s in scripts:
            if any(k in s for k in ['gtraffic', 'pages.dev', 'ontops', 'trade', 'mammon', 'bt', 'traffic']):
                print("FOUND TRAFFIC SCRIPT:", s)
except Exception as e:
    print("Error:", e)
