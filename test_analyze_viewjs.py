with open('scratch_link4m_view.js', 'r', encoding='utf-8') as f:
    js = f.read()

import re
matches = re.findall(r'function\s+checkPassword[^{]*\{[^}]+(?:\{[^}]+(?:\{[^}]+(?:\{[^}]+)?[^}]*\})?[^}]*\})?', js)
for m in matches:
    print('checkPassword fn:\n', m[:1000])

ajax_calls = re.findall(r'\$\.ajax\(\{[^\}]+\}', js)
for a in ajax_calls:
    print('Ajax call:\n', a[:300])

print("\n--- All function names ---")
fns = re.findall(r'function\s+([a-zA-Z0-9_]+)\s*\(', js)
print(set(fns))
