with open('research/link4m_scripts/link4m_org_view.js', 'r', encoding='utf-8') as f:
    js = f.read()

import re
m_arr = re.search(r'var _0x39d2c4=\[([\s\S]*?)\];', js)
if m_arr:
    raw = m_arr.group(1)
    strings = [s.strip('\'"') for s in re.findall(r'[\x27\x22]([^\x27\x22]*)[\x27\x22]', raw)]

    # In the JS, the array is rotated in a loop:
    # while (true) { try { ... if (_0xf715cc === _0x9cce7b) break; else arr.push(arr.shift()); } ... }
    # Let's run the exact rotation in node
    print("Array extracted. Total strings:", len(strings))
