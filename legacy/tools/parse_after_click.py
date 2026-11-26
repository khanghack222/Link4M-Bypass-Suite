import re

with open("data/temp/123bloom_after_click.html", "r", encoding="utf-8") as f:
    html = f.read()

print("HTML size:", len(html))

# Find traffic-button-no
for m in re.finditer(r'<div[^>]*traffic-button-no[^>]*>.*?</div>', html, re.DOTALL):
    print("Found traffic-button-no:", m.group(0))

# Search for any modals or iframes or new divs inserted
for m in re.finditer(r'<div[^>]*(?:captcha|modal|math|ontop)[^>]*>.*?</div>', html, re.DOTALL | re.IGNORECASE):
    print("Found captcha/modal div:", m.group(0)[:300])

# Search for all script tags added
scripts = re.findall(r'<script[^>]*src=[\'"]([^\'"]+)[\'"]', html)
for s in scripts:
    if "traffic" in s or "ontop" in s:
        print("Script:", s)
