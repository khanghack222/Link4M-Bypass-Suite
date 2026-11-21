import requests
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.google.com/'
}

r = requests.get('https://khovatlieunoithatdanang.com/?s=van+phu+phim', headers=headers, timeout=10)
print('Search status:', r.status_code)

links = re.findall(r'href=["\'](https://khovatlieunoithatdanang\.com/[^"\']+)["\']', r.text)
links = list(dict.fromkeys(links))
for l in links:
    if 'van-ep-cop-pha-phu-phim' in l or 'phu-phim' in l or 'van-phu-phim' in l or 'post' in l or 'bai-viet' in l or 'san-pham' in l:
        print('Post:', l)
