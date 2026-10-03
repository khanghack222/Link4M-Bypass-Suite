with open('test_onlinejob_route.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for l in lines:
    if '4JilBaPXK' in l and 'locator' in l:
        new_lines.append("    btn = page.locator(\"[id='4JilBaPXK']\")\n")
    else:
        new_lines.append(l)

with open('test_onlinejob_route.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Fixed lines!')
