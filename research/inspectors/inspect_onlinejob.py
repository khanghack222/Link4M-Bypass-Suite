import requests, re
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://onlinejob.com.co', headers=headers)
scripts = re.findall(r'<script[^>]*src=[\"\']([^\"\']+)[\"\']', r.text)
for s in scripts:
    if any(k in s for k in ['layma', 'traffic', 'captcha', 'widget']):
        print('Script src:', s)
for s_inline in re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL):
    if 'layma' in s_inline.lower():
        print('Inline snippet:', s_inline.strip()[:400])
