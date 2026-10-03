with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import sys
sys.stdout.reconfigure(encoding='utf-8')

idx = text.find('const checkScrollUpDown =')
if idx == -1:
    idx = text.find('function checkScrollUpDown')
print(text[idx:idx+1200])
