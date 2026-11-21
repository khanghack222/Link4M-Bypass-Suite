import requests
import sys
import json
import uuid
import time
import re

sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
client_id = str(uuid.uuid4())

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://khovatlieunoithatdanang.com/van-ep-phu-phim-da-nang',
    'Origin': 'https://khovatlieunoithatdanang.com',
    'Accept': '*/*',
}

# 1. Fetch fresh service-v3.js
print('1. Fetching service-v3.js...')
r = session.get('https://s1.what-on.com/widget/service-v3.js?key=VkanofiI', headers=headers)

def unhex(m):
    return chr(int(m.group(1), 16))

text = re.sub(r'\\x([0-9a-fA-F]{2})', unhex, r.text)

vars_found = re.findall(r'var\s+([a-zA-Z0-9_]+)\s*=\s*["\']([^"\']+)["\'];', text)
key = vars_found[0][1]
g_code = vars_found[1][1]
o_host = vars_found[2][1]
v_session = vars_found[3][1]

print(f'Key: {key}, Host: {o_host}, Session: {v_session}, Hash: {g_code}')

# Client params
jscd = {
    'screen': '1920x1080',
    'browser': 'Chrome',
    'browserVersion': '120.0.0.0',
    'browserMajorVersion': '120',
    'mobile': 'false',
    'os': 'Windows',
    'osVersion': '10',
    'cookies': 'true',
    'flashVersion': 'no check',
    'client_id': client_id,
    'pathname': '/van-ep-phu-phim-da-nang',
    'href': 'https://khovatlieunoithatdanang.com/van-ep-phu-phim-da-nang',
    'hostname': 'khovatlieunoithatdanang.com'
}

post_data = {
    'traffic_session': v_session,
    'key': key
}
post_data.update(jscd)

print('2. Sending client.js ping...')
c_res = session.post(f'https://{o_host}/widget/client.js', headers=headers, data=post_data)
print('Client ping status:', c_res.status_code, 'len:', len(c_res.text))

# 3. Poll get_quest_code.html every 10 seconds up to 70 seconds
get_params = {
    'code': g_code,
    'traffic_session': v_session,
    'key': key
}
get_params.update(jscd)

print('3. Polling get_quest_code.html...')
start = time.time()
while time.time() - start <= 70:
    elapsed = int(time.time() - start)
    q_res = session.get(f'https://{o_host}/widget/get_quest_code.html', headers=headers, params=get_params)
    print(f'[{elapsed}s] Quest code response: {q_res.text}')
    try:
        data = q_res.json()
        if data.get('success'):
            print('SUCCESS CODE FOUND:', data)
            break
    except Exception as e:
        pass
    time.sleep(10)
