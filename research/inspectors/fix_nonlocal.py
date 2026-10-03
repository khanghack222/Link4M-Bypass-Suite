with open('test_full_layma.py', 'r', encoding='utf-8') as f:
    text = f.read()
text = text.replace('nonlocal extracted_code', 'global extracted_code')
with open('test_full_layma.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed nonlocal!')
