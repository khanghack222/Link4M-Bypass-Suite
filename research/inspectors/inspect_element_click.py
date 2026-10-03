with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re, sys
sys.stdout.reconfigure(encoding='utf-8')

matches = [m.start() for m in re.finditer(r'element\.(?:onclick|addEventListener\([\'\"]click)', text)]
for idx in matches:
    print('--- element click ---')
    print(text[max(0, idx-50):min(len(text), idx+300)])
