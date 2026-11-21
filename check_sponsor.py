import requests
import re
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

try:
    r = requests.get('https://tylenhacai100.io', headers=headers, timeout=10)
    print('Status:', r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    scripts = [s.get('src') for s in soup.find_all('script') if s.get('src')]
    for s in scripts:
        print('Script:', s)
    inline_scripts = [s.text for s in soup.find_all('script') if not s.get('src')]
    for s in inline_scripts:
        if 'traffic' in s.lower() or 'link4m' in s.lower() or 'button-lay-ma' in s.lower() or 'code' in s.lower():
            print('Inline match snippet:', s[:300])
except Exception as e:
    print('Error:', e)
