import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
from rapidocr_onnxruntime import RapidOCR

imgs = [
    'https://bbmkts.com/uploads/img_6a8b1196509f27_98029762.jpg',
    'https://bbmkts.com/uploads/img_6a8b118f125768_72968162.png',
    'https://bbmkts.com/uploads/img_694939ceda8d12_63703177.png'
]

ocr = RapidOCR()
for i, url in enumerate(imgs):
    fname = f"step_{i}.png"
    urllib.request.urlretrieve(url, fname)
    lines, _ = ocr(fname)
    print(f"\n=== OCR FOR {url} ===")
    if lines:
        for l in lines:
            print("  *", l[1])
