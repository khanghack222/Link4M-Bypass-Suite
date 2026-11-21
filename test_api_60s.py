import requests
import time
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://tylenhacai100.io/',
    'Origin': 'https://tylenhacai100.io',
    'Content-Type': 'application/x-www-form-urlencoded'
}

# 1. Fetch fresh service-v2.js
print("[1] Fetching fresh widget script...")
r_js = requests.get('https://s1.what-on.com/widget/service-v2.js?key=5zqDZ7qw', headers=headers)
v_match = re.search(r"var v9901a = '([^']+)'", r_js.text)
b_match = re.search(r'var b990b3 = "([^"]+)"', r_js.text)
v9901a = v_match.group(1) if v_match else '6aef40da8ffae330b704b7ab'
b990b3 = b_match.group(1) if b_match else '74b68fa011bbc2bf3a63ce79f9eb2f0f'
print('Session:', v9901a)
print('Code hash:', b990b3)

# 2. Post client.js initialization
print("[2] Initializing client session...")
data = {
    'traffic_session': v9901a,
    'key': '5zqDZ7qw',
    'client_id': '11223344-5566-7788-9900-aabbccddeeff',
    'pathname': '/',
    'href': 'https://tylenhacai100.io/',
    'hostname': 'tylenhacai100.io'
}
r1 = session.post('https://s1.what-on.com/widget/client.js', data=data, headers=headers)
print('Client.js status:', r1.status_code)

# 3. Wait exactly 62 seconds as required by backend
print("[3] Waiting 62 seconds for backend countdown...")
for i in range(12):
    time.sleep(5)
    print(f"  ... waited {(i+1)*5}s / 60s")
time.sleep(2)

# 4. Request quest code Step 1
print("[4] Requesting Step 1 quest code...")
params = {
    'code': b990b3,
    'traffic_session': v9901a,
    'key': '5zqDZ7qw',
    'client_id': '11223344-5566-7788-9900-aabbccddeeff',
    'pathname': '/',
    'href': 'https://tylenhacai100.io/',
    'hostname': 'tylenhacai100.io'
}
r2 = session.get('https://s1.what-on.com/widget/get_quest_code.html', params=params, headers=headers)
print('Step 1 status:', r2.status_code)
print('Step 1 response:', r2.text)

try:
    res1 = r2.json()
    if res1.get('id'):
        print(f"[5] Step 1 success! Got ID: {res1['id']}")
        time.sleep(2)
        params['id'] = res1['id']
        r3 = session.get('https://s1.what-on.com/widget/get_quest_code.html', params=params, headers=headers)
        print('Step 2 response:', r3.text)
except Exception as e:
    print('Error parsing response:', e)
