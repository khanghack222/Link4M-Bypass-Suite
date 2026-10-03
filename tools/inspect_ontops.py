import urllib.request, re, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = "https://123bloom.com"
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.google.com/"
})
html = urllib.request.urlopen(req, context=ctx, timeout=10).read().decode("utf-8", errors="ignore")
scripts = re.findall(r'<script[^>]*src=[\'"]([^\'"]+)[\'"]', html)
print(f"Total scripts found: {len(scripts)}")
for s in scripts:
    print(" ->", s)

# Also check for inline widget or ontops
for m in re.finditer(r'(?:ontops|process-code|traffic)[^"\']*', html):
    print("Match in HTML:", m.group(0))
