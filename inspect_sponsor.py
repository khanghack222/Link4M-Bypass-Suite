import requests
import re

try:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    r = requests.get("https://nydependablelawncare.com", headers=headers, timeout=10)
    print("Sponsor Status:", r.status_code)
    scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', r.text)
    for s in scripts:
        if any(k in s.lower() for k in ["traffic", "link", "code", "token", "ma", "widget", "s1", "app", "4m"]):
            print("Sponsor widget script:", s)
            
    # Also search inline scripts
    inlines = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.S)
    for inl in inlines:
        if any(k in inl.lower() for k in ["link4m", "s1.link4m", "lay-ma", "layma", "campaign"]):
            print("Inline match snippet:", inl[:200])
except Exception as e:
    print("Error:", e)
