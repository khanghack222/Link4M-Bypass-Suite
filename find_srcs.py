import re

with open("link4m_page.html", "r", encoding="utf-8") as f:
    text = f.read()

srcs = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', text)
for s in srcs:
    print("SCRIPT SRC:", s)
