import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/what_on.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's decode \x hex strings
def unhex(m):
    return chr(int(m.group(1), 16))

decoded = re.sub(r'\\x([0-9a-fA-F]{2})', unhex, text)
with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/what_on_decoded.js', 'w', encoding='utf-8') as f:
    f.write(decoded)

print('Saved what_on_decoded.js!')

# Look for ajax, fetch, endpoints in decoded
for m in re.finditer(r'url\s*:\s*([^,\n}]+)', decoded):
    print('URL:', m.group(0))

for m in re.finditer(r'function\s+([a-zA-Z0-9_]+)\s*\(', decoded):
    print('Function:', m.group(1))
