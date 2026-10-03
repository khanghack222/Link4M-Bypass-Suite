with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re, sys
sys.stdout.reconfigure(encoding='utf-8')

idx = 0
for _ in range(5):
    idx = text.find('getElementById(traffic_key)', idx+1)
    if idx == -1: break
    print('--- getElementById(traffic_key) ---')
    print(text[max(0, idx-100):min(len(text), idx+400)])
