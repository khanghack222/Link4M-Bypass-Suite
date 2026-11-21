import json
import re
import base64
from rapidocr_onnxruntime import RapidOCR

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/dumped_advertise.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

html = data.get('html', '')
imgs = re.findall(r'data:image/[^;]+;base64,([^"]+)', html)
print('Found images:', len(imgs))

ocr = RapidOCR()
for i, img_b64 in enumerate(imgs):
    b = base64.b64decode(img_b64)
    res, _ = ocr(b)
    print(f'=== Image {i+1} ===')
    if res:
        for line in res:
            print(' ', line[1])
