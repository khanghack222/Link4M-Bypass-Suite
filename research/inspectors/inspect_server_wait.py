with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import sys
sys.stdout.reconfigure(encoding='utf-8')

idx = text.find('function hasCompletedServerWait')
print(text[idx:idx+800])
