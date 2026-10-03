import json, re
data = json.load(open('adv.json', encoding='utf-8'))
for k in data:
    if k != 'html':
        print(k, ':', data[k])
html = data.get('html', '')
clean = re.sub(r'src="data:image/[^"]+"', 'src="[IMG]"', html)
print('\nCLEAN HTML:')
print(clean)
