with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re, sys
sys.stdout.reconfigure(encoding='utf-8')

matches = [m.start() for m in re.finditer(r'addEventListener\([\'\"]click', text)]
for idx in matches:
    print('--- click listener ---')
    print(text[max(0, idx-100):min(len(text), idx+400)])
