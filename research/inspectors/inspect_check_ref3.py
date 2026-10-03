import re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('const checkReferer =')
print(text[idx:idx+700])
