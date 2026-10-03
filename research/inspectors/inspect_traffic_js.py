import re

with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

endpoints = set(re.findall(r'[\'\"](\/api\/[^\'\"]+)[\'\"]', text))
print('Endpoints found:', endpoints)

# Find getcode payload
idx = text.find('/api/traffic/getcode')
if idx != -1:
    print('--- /api/traffic/getcode context ---')
    print(text[max(0, idx-300):min(len(text), idx+600)])

# Find /api/admin/campain context
idx2 = text.find('/api/admin/campain')
if idx2 != -1:
    print('--- /api/admin/campain context ---')
    print(text[max(0, idx2-200):min(len(text), idx2+500)])
