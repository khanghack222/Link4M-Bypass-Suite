import requests
import re
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'vi,en;q=0.9',
})

alias = '68pw167Y'
r1 = s.get(f'https://link4m.net/go/{alias}')
print('Link4M Cookies:', s.cookies.get_dict())

m_code = re.search(r'data-code\s*=\s*["\']([a-f0-9]+)["\']', r1.text)
code = m_code.group(1) if m_code else ''
print('Extracted code len:', len(code))

headers_api = {
    'Referer': f'https://link4m.net/go/{alias}',
    'Origin': 'https://link4m.net',
    'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
}

data = {
    'alias': alias,
    'codes': code
}
r2 = s.post('https://s1.link4m.app/api/campaign/get-advertise', headers=headers_api, data=data)
res = r2.json()
html = res.get('html', '')
imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
print(f"Total images in campaign: {len(imgs)}")
import base64
try:
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    print("\n--- OCR DECODING SPONSOR IMAGES ---")
    for i in range(min(4, len(imgs))):
        img_b64 = imgs[i]
        if img_b64.startswith('data:image'):
            raw = base64.b64decode(img_b64.split('base64,')[1])
            res, _ = ocr(raw)
            txt = ' '.join([r[1] for r in res]) if res else ''
            print(f"Img {i} OCR text: '{txt}'")
except Exception as e:
    print("OCR error:", e)

text_clean = re.sub(r'<[^>]+>', ' ', html)
lines = [l.strip() for l in text_clean.split('  ') if len(l.strip()) > 3]
print('\nCampaign Text Steps:')
for l in lines[:25]:
    print(' ->', l)
