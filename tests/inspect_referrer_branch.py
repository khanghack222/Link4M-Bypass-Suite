import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('src/core/btd_deob.js', 'r', encoding='utf-8') as f:
    code = f.read()

target = 'if (document["referrer"]["includes"]'
p = code.find(target)
print("Position:", p)
print(code[p:p+1200])
