import re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'function\s+\w*refer\w*', text, re.IGNORECASE)
if m:
    print('Found function:', m.group(0))
    idx = m.start()
    print(text[idx:idx+600])
else:
    print('No function with refer found')
    # search where checkReferer is called
    idx = text.find('checkReferer')
    print('Where checkReferer is called:')
    print(text[max(0, idx-200):idx+300])
