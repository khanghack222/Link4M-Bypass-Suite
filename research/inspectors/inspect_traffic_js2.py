import re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('buildCampainUrl')
if idx == -1:
    idx = text.find('/api/admin/campain')
print(text[max(0, idx-600):idx+300])
