import json
import re
import base64

with open('scratch_link4m_advertise.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

html = d['data']['html']
imgs = re.findall(r'src=["\']([^"\']+)["\']', html)
print(f"Total imgs: {len(imgs)}")
for i, x in enumerate(imgs):
    print(f"Img {i}: len={len(x)}, prefix={x[:35]}")
    if x.startswith("data:image/"):
        b64_data = x.split(",", 1)[1]
        raw_b = base64.b64decode(b64_data)
        with open(f"scratch_img_{i}.png", "wb") as f_out:
            f_out.write(raw_b)
        print(f"Saved scratch_img_{i}.png ({len(raw_b)} bytes)")
