import json
data = json.load(open('adv.json', encoding='utf-8'))
with open('form.txt', 'w', encoding='utf-8') as f:
    f.write(data.get('form', ''))
with open('html_clean.txt', 'w', encoding='utf-8') as f:
    f.write(data.get('html', ''))
print('Saved form.txt and html_clean.txt')
