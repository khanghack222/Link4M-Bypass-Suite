import sys
sys.stdout.reconfigure(encoding='utf-8')
from bs4 import BeautifulSoup

with open('current_campaign.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print("All elements in order:")
for tag in soup.find_all(['p', 'span', 'b', 'strong', 'li', 'h4', 'div']):
    # Only direct text
    t = tag.find(text=True, recursive=False)
    if t:
        txt = t.strip()
        if txt and len(txt) > 2:
            print("TXT:", txt)

for img in soup.find_all('img'):
    src = img.get('src')
    if src and not src.startswith('data:'):
        print("IMG:", src)
