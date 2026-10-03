with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re, sys
sys.stdout.reconfigure(encoding='utf-8')

for m in re.finditer(r'Ẩn danh|an danh|incognito|private', text, re.IGNORECASE):
    idx = m.start()
    print('--- Incognito detection match ---')
    print(text[max(0, idx-200):min(len(text), idx+300)])
