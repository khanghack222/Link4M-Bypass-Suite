import re

with open('scratch_whaton_service_v3.js', 'r', encoding='utf-8') as f:
    js = f.read()

urls = re.findall(r'https?://[^\s"\'`]+|//[a-zA-Z0-9\.\-_/]+', js)
print('URLs in service-v3.js:')
for u in set(urls):
    if any(k in u for k in ['what-on', 'api', 'widget', 'campaign', 'get', 'code', 'click']):
        print(' -', u)

ajax_calls = re.findall(r'\$\.ajax\(\{[^\}]+\}', js)
print(f'Ajax calls found: {len(ajax_calls)}')
for a in ajax_calls[:5]:
    print('Ajax:', a.replace('\n', ' ')[:200])

post_gets = re.findall(r'\$\.(?:post|get)\([^\)]+\)', js)
print(f'Post/Get calls found: {len(post_gets)}')
for p in post_gets[:5]:
    print('Post/Get:', p.replace('\n', ' ')[:200])
