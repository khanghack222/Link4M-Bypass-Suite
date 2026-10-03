with open('src/core/btd.js', 'r', encoding='utf-8') as f:
    code = f.read()

import re
matches = [m.start() for m in re.finditer(r'NEXUS_API_GATEWAY', code)]
for pos in matches:
    print('pos:', pos)
    print(code[max(0, pos-150):min(len(code), pos+150)])
