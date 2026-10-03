with open('src/core/btd.js', 'r', encoding='utf-8') as f:
    code = f.read()

arr_code = code[code.find('function _0x30bd()'):]
arr_code = arr_code[:arr_code.find('];')]
words = [w.strip(' \n\r\t"\'') for w in arr_code.split(',')]
for param in [2246, 2390, 2422, 1777, 1830]:
    idx = param - 424
    print(param, '->', repr(words[idx]))
