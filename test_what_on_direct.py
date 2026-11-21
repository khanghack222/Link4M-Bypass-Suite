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
r = session.get('https://s1.what-on.com/widget/service-v3.js?key=VkanofiI', headers=headers)

# Unescape \xNN
def unhex(m):
    return chr(int(m.group(1), 16))

text = re.sub(r'\\x([0-9a-fA-F]{2})', unhex, r.text)

# Extract first 5 var assignments
vars_found = re.findall(r'var\s+([a-zA-Z0-9_]+)\s*=\s*["\']([^"\']+)["\'];', text)
print('Variables found:', vars_found[:6])

key = vars_found[0][1]
g_code = vars_found[1][1]
o_host = vars_found[2][1]
v_session = vars_found[3][1]
uuid_name = vars_found[4][1]

print('Key:', key)
print('Code hash:', g_code)
print('Host:', o_host)
print('Traffic session:', v_session)
print('UUID name:', uuid_name)

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

# 2. Trigger client.js
post_data = {
    'traffic_session': v_session,
    'key': key
}
post_data.update(jscd)

print('Sending client.js ping...')
c_res = session.post(f'https://{o_host}/widget/client.js', headers=headers, data=post_data)
print('Client ping status:', c_res.status_code)
print('Client ping response:', c_res.text[:200])

# 3. Test get_quest_code.html
print('Testing get_quest_code.html...')
get_params = {
    'code': g_code,
    'traffic_session': v_session,
    'key': key
}
get_params.update(jscd)

q_res = session.get(f'https://{o_host}/widget/get_quest_code.html', headers=headers, params=get_params)
print('Quest code status:', q_res.status_code)
print('Quest code response:', q_res.text)
