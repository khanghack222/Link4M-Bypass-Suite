import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scratch_whaton_service_v3.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if any(k in line for k in ['url:', '$.ajax', '$.post', '$.get', 'get_quest_code', 'get_code', 'process-site', 'check-site', 'click.html', 'what-on.com']):
        print(f'Line {i+1}: {line.strip()[:160]}')
