import re

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/what_on.js', 'r', encoding='utf-8') as f:
    text = f.read()

urls = re.findall(r'https?://[a-zA-Z0-9\.\-\_\/\?\=\&\%\#]+', text)
for u in sorted(set(urls)):
    print('URL found:', u)
