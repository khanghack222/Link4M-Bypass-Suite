with open('scratch_link4m_view.js', 'r', encoding='utf-8') as f:
    js = f.read()

import re
matches = re.findall(r'api_domain\s*\+\s*["\']([^"\']+)["\']', js)
print('All api_domain endpoints in view.js:')
for m in set(matches):
    print(' -', m)

# Also check any string starting with /api/ or /links/
paths = re.findall(r'["\'](/(?:api|links|widget|campaign)/[^"\']+)["\']', js)
print('All paths in view.js:')
for p in set(paths):
    print(' -', p)
