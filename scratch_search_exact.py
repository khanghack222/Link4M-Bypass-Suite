import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages'))
from curl_cffi import requests
from bs4 import BeautifulSoup

q = '"Trang chơi cho phép giải trí dễ dàng trên web"'
url = f'https://html.duckduckgo.com/html/?q={requests.utils.quote(q)}'
r = requests.get(url, impersonate='chrome124', timeout=8, verify=False)
soup = BeautifulSoup(r.text, 'html.parser')
for res in soup.select('.result'):
    title = res.select_one('.result__title')
    snip = res.select_one('.result__snippet')
    u = res.select_one('.result__url')
    print("Title:", title.get_text().strip() if title else "")
    print("URL:", u.get_text().strip() if u else "")
    print("Snippet:", snip.get_text().strip() if snip else "")
    print("-" * 40)
