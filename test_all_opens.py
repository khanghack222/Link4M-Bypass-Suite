with open('scratch_whaton_service_v3.js', 'r', encoding='utf-8') as f:
    js = f.read()

import re
opens = re.findall(r'xmlhttp\.open\([^\)]+\)', js)
for o in opens:
    print('xmlhttp.open:', o)
