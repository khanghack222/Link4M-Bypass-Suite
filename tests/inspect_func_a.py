with open('src/core/btd.js', 'r', encoding='utf-8') as f:
    code = f.read()

pos = 31446
print(code[pos-1000:pos+200])
