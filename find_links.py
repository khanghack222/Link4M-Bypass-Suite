import requests
import re

cookies = {
    'auth_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MjQzMDQwMDEsImhhc2giOiJmZjNiNjIyNThiMDZkNWUzZmZiYzgxZTkzZjM0Zjg4YSIsImlhdCI6MTc4NjA4NzMzMn0.Ls84yF9wPxkRviEFo5xbW8iB5oKC8ej7x75aHlaVOvM',
}
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
r = requests.get('https://2captcha.com/enterpage', cookies=cookies, headers=headers)
links = re.findall(r'href=["\']([^"\']+)["\']', r.text)
for l in set(links):
    if any(k in l.lower() for k in ['customer', 'client', 'worker', 'switch', 'setting', 'api', 'dashboard']):
        print(l)
