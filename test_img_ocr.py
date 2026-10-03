import json, base64
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
data = json.load(open('adv.json', encoding='utf-8'))
b64s = [m for m in data.get('html', '').split('data:image/png;base64,')[1:]]
for idx, b in enumerate(b64s):
    raw = b.split('"')[0]
    img = base64.b64decode(raw)
    res, _ = ocr(img)
    print(f'IMG {idx}:', [r[1] for r in res] if res else [])
