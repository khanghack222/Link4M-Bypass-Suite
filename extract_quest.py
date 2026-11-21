import json
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/fresh_adv.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

html = d.get('html', '')
print("--- Text in paragraph tags ---")
for p in re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
    clean = re.sub(r'<[^>]+>', ' ', p).strip()
    clean = ' '.join(clean.split())
    if clean:
        print(clean)

print("\n--- External Image URLs ---")
for img in re.findall(r'src=["\'](http[^"\']+)["\']', html):
    print(img)

print("\n--- Base64 Images Count ---")
b64s = re.findall(r'src=["\'](data:image/[^;]+;base64,[^"\']+)["\']', html)
print(f"Found {len(b64s)} base64 images.")
for i, b in enumerate(b64s):
    header, data = b.split(',', 1)
    import base64
    filename = f'C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/step_{i}.png'
    with open(filename, 'wb') as img_f:
        img_f.write(base64.b64decode(data))
    print(f"Saved {filename}")
