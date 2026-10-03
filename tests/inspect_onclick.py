import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('src/core/btd_deob.js', 'r', encoding='utf-8') as f:
    code = f.read()

target = 'nexusTicksLeft, 0)) p["mkuxh"](requestAnimationFrame, A); else {'
p = code.find(target)
print("Position:", p)
print(code[p:p+2500])
