with open('test_full_layma.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(\"sys.stdout.reconfigure(encoding='utf-8')\", \"sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)\")
text = text.replace(\"wait_until='networkidle'\", \"wait_until='domcontentloaded'\")

with open('test_full_layma.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed domcontentloaded and line_buffering!')
