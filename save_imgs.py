import requests
import re
import base64
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Run probe and save images
import test_probe_link4m
imgs = test_probe_link4m.imgs

for i, img_b64 in enumerate(imgs[:4]):
    if img_b64.startswith('data:image'):
        raw = base64.b64decode(img_b64.split('base64,')[1])
        filename = f'C:\\Users\\XUAN\\.gemini\\antigravity\\scratch\\Link4M_Bypass_Suite\\step_img_{i}.png'
        with open(filename, 'wb') as f:
            f.write(raw)
        print(f"Saved {filename}")
