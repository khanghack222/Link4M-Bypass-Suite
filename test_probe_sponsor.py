import requests
import re
import urllib3
import sys

sys.stdout.reconfigure(encoding='utf-8')
urllib3.disable_warnings()

url = 'https://789-club.cc'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://www.google.com/'
}

try:
    r = requests.get(url, verify=False, timeout=10, headers=headers)
    print(f"{url} Status: {r.status_code}, Length: {len(r.text)}")

    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', r.text)
    print('\nScripts in page:')
    for s in scripts:
        print(' -', s)

    inline = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
    print(f"\nTotal inline scripts: {len(inline)}")
    for s in inline:
        if any(k in s for k in ['traffic', 'what-on', 'yoads', 'traffic_key', 'traffic_domain', 'traffic_id', 'service.js']):
            print('\n[+] Found Traffic Widget Script:')
            print(s.strip()[:1000])

    # Check for direct code elements
    for el in re.findall(r'<[^>]+(?:traffic|whaton|layma|token|code)[^>]*>', r.text, re.I):
        print('Element candidate:', el)

except Exception as e:
    print("Error connecting to sponsor:", e)
