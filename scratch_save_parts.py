import json

with open('scratch_link4m_advertise.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
data = d.get('data', {})

with open('scratch_link4m_html.html', 'w', encoding='utf-8') as f_out:
    f_out.write(data.get('html', ''))

with open('scratch_link4m_run.js', 'w', encoding='utf-8') as f_out:
    f_out.write(data.get('run', ''))

print("Saved scratch_link4m_html.html and scratch_link4m_run.js!")
