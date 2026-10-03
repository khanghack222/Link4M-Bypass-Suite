import re

with open('scratch_b2a.js', 'r', encoding='utf-8') as f:
    c = f.read()

matches = re.findall(r'(?:querySelector|getElementById)\s*\(\s*["\']([^"\']+)["\']', c)
print("DOM selectors:", set(matches))

urls = re.findall(r'https?://[^"\'\s)]+', c)
print("URLs found:", set(urls))

api_endpoints = re.findall(r'["\'](/[^"\']+)["\']', c)
apis = [a for a in api_endpoints if any(k in a for k in ['api', 'code', 'token', 'traffic', 'btn', 'track', 'load'])]
print("APIs found:", set(apis))

# Check for button labels
btn_texts = re.findall(r'["\']([^"\']*(?:LẤY|MÃ|CODE|WAIT|GIÂY|CLICK|XÁC NHẬN)[^"\']*)["\']', c, re.I)
print("Button texts:", set(btn_texts[:10]))
