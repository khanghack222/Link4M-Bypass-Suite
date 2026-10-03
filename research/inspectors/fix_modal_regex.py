with open('test_qcaptcha_modal.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('r\"var\\s+traffic_key\\s*=\\s*[\'\\\"]([^\'\\\"]+)[\'\\\"]\"', \"r'var\\\\s+traffic_key\\\\s*=\\\\s*[\\'\\\"]([^\\'\\\"]+)[\\'\\\"]'\")
with open('test_qcaptcha_modal.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed regex!')
