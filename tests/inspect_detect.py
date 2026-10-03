with open('src/core/btd.js', 'r', encoding='utf-8') as f:
    code = f.read()

import re
matches = [m.start() for m in re.finditer(r'detectIncognito', code)]
for pos in matches:
    print('detectIncognito at pos:', pos)
    print(code[max(0, pos-200):min(len(code), pos+300)])
