import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/client_response.js', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'function\s+([a-zA-Z0-9_]+)\(\)\{\s*var\s+[a-zA-Z0-9_]+=\[(.*?)\];\s*\1=', text, re.DOTALL)
if m:
    print('Found string array function:', m.group(1))
    arr_str = m.group(2)
    # Split items by comma respecting quotes
    items = re.findall(r'["\'](.*?)["\']', arr_str)
    print(f'Total string literals: {len(items)}')
    interesting = []
    for it in items:
        # unescape hex
        try:
            dec = re.sub(r'\\x([0-9a-fA-F]{2})', lambda x: chr(int(x.group(1), 16)), it)
        except Exception:
            dec = it
        if any(w in dec.lower() for w in ['http', 'cookie', 'token', 'post', 'get', 'api', 'widget', 'session', 'hash', 'mouse', 'scroll', 'time', 'click', 'step']):
            interesting.append(dec)
    print('Interesting strings (sample 30):')
    for s in list(set(interesting))[:30]:
        print('-', s)
else:
    print('String array regex did not match')
