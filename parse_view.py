import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/view.js', 'r', encoding='utf-8') as f:
    code = f.read()

# Let's extract the array definition and decoder
# Usually: var _0x... = [...]; function _0x...() { ... }
# Let's find where the main logic starts.
lines = code.split(';')
print("Total semicolon-separated parts:", len(lines))
for i, line in enumerate(lines[:30]):
    print(f"{i}: {line[:120]}")
