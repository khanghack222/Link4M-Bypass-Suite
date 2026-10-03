import urllib.request
from rapidocr_onnxruntime import RapidOCR
import re

img_url = 'https://bbmkts.com/uploads/img_6a9a2b1a162aa2_23092712.jpg'
tmp = 'test_img.jpg'
urllib.request.urlretrieve(img_url, tmp)
ocr = RapidOCR()
lines, _ = ocr(tmp)
texts = [l[1] for l in lines]
print("All OCR texts:")
for t in texts:
    print(" -", t)
