import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/client_response.js', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'function\s+([a-zA-Z0-9_]+)\(\)\{\s*var\s+[a-zA-Z0-9_]+=\[(.*?)\];\s*\1=', text, re.DOTALL)
items = re.findall(r'["\'](.*?)["\']', m.group(2))
with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/strings.txt', 'w', encoding='utf-8') as out:
    for it in items:
        try:
            dec = re.sub(r'\\x([0-9a-fA-F]{2})', lambda x: chr(int(x.group(1), 16)), it)
        except Exception:
            dec = it
        out.write(dec + '\n')
print('Dumped', len(items), 'strings to strings.txt')
