with open('traffic_index_4JilBaPXK.js', 'r', encoding='utf-8') as f:
    text = f.read()

import sys
sys.stdout.reconfigure(encoding='utf-8')

idx = text.find('xacthucButton.style.display =')
if idx != -1:
    print('--- xacthucButton display ---')
    print(text[max(0, idx-200):idx+300])

idx2 = text.find('showCaptchaModalForGetCode')
if idx2 != -1:
    print('--- showCaptchaModalForGetCode ---')
    print(text[max(0, idx2-100):idx2+400])
