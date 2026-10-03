import re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

matches = [m.start() for m in re.finditer('buildCampainUrl', text)]
for idx in matches:
    print('--- call site ---')
    print(text[max(0, idx-100):min(len(text), idx+300)])
